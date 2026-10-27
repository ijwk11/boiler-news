"""보일러 업계 아침 뉴스 페이지 생성기.

keywords.txt 의 묶음별 검색어로 구글 뉴스 RSS에서 최근 기사를 모아
묶음 순서대로 정리하고, 헤드라인에 자주 나온 '이슈 키워드'를 뽑아
site/index.html 한 장으로 만듭니다. 파이썬 기본 라이브러리만 사용합니다.

사용법:  python fetch_news.py
"""
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

KST = timezone(timedelta(hours=9))
BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "site"

LOOKBACK_HOURS = 48     # 최근 몇 시간 이내 기사만 모을지
MAX_PER_GROUP = 15      # 묶음당 최대 기사 수
ISSUE_TOP = 10          # 이슈 키워드 최대 개수
ISSUE_MIN = 2           # 최소 몇 개 기사에 나와야 이슈 키워드로 볼지

PARTICLES = ("에서는", "으로는", "에서", "으로", "에게", "까지", "부터", "처럼",
             "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만")


# ---------- 설정 읽기 ----------
def read_lines(name):
    p = BASE / name
    if not p.exists():
        return []
    lines = [l.strip() for l in p.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l and not l.startswith("#")]


def read_groups():
    """'묶음이름: 검색어1, 검색어2' 형식. 콜론이 없으면 줄 전체가 이름이자 검색어."""
    groups = []
    for line in read_lines("keywords.txt"):
        if ":" in line:
            name, terms = line.split(":", 1)
            terms = [t.strip() for t in terms.split(",") if t.strip()]
        else:
            name, terms = line, [line]
        name = name.strip()
        if name and terms:
            groups.append({"name": name, "terms": terms})
    return groups


def read_stopwords():
    words = set()
    for line in read_lines("stopwords.txt"):
        words.update(line.split())
    return words


# ---------- 수집 ----------
def fetch_rss(term):
    q = urllib.parse.quote(f"{term} when:2d")
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (boiler-news-bot)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def parse_items(xml_bytes):
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        source = (it.findtext("source") or "").strip()
        pub = it.findtext("pubDate")
        if not title or not link:
            continue
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)].strip()
        try:
            dt = parsedate_to_datetime(pub).astimezone(KST) if pub else None
        except (TypeError, ValueError):
            dt = None
        items.append({"title": title, "link": link, "source": source, "dt": dt})
    return items


def norm(title):
    return re.sub(r"[\W_]+", "", title).lower()


def collect(groups):
    excludes = read_lines("exclude.txt")
    cutoff = datetime.now(KST) - timedelta(hours=LOOKBACK_HOURS)
    seen, results, errors = set(), [], []

    for g in groups:
        for term in g["terms"]:
            try:
                items = parse_items(fetch_rss(term))
            except Exception as e:  # 한 검색어가 실패해도 나머지는 계속
                errors.append(f"{term}: {e}")
                continue
            for i in items:
                if i["dt"] is not None and i["dt"] < cutoff:
                    continue
                key = norm(i["title"])
                if key in seen or any(x in i["title"] for x in excludes):
                    continue
                seen.add(key)
                i["group"] = g["name"]
                results.append(i)

    # 제목에 회사명 등 더 구체적인 검색어가 있으면 그 묶음으로 옮깁니다.
    # (예: '보일러'로 검색됐어도 제목에 '경동나비엔'이 있으면 경동나비엔 묶음으로)
    heads = [(g["name"], t.split()[0]) for g in groups for t in g["terms"]]
    all_heads = [h for _, h in heads]
    specific = [(n, h) for n, h in heads if not any(h != o and h in o for o in all_heads)]
    for i in results:
        for n, h in specific:
            if h in i["title"]:
                i["group"] = n
                break

    results.sort(key=lambda i: i["dt"] or cutoff, reverse=True)
    trimmed, counts = [], Counter()
    for i in results:
        if counts[i["group"]] < MAX_PER_GROUP:
            counts[i["group"]] += 1
            trimmed.append(i)
    return trimmed, errors


# ---------- 이슈 키워드 ----------
def tokens(title):
    out = set()
    for w in re.findall(r"[0-9A-Za-z가-힣]+", title):
        for p in PARTICLES:
            if len(w) > len(p) + 1 and w.endswith(p):
                w = w[: -len(p)]
                break
        if len(w) >= 2 and not w.isdigit():
            out.add(w)
    return out


def issue_keywords(items, groups):
    stop = read_stopwords()
    keyword_bits = set()
    for g in groups:
        keyword_bits.add(g["name"])
        for t in g["terms"]:
            keyword_bits.update(t.split())
            keyword_bits.add(t.replace(" ", ""))
    c = Counter()
    for i in items:
        for w in tokens(i["title"]):
            if w in stop or any(w == k or w in k or k in w for k in keyword_bits):
                continue
            c[w] += 1
    return [(w, n) for w, n in c.most_common(ISSUE_TOP) if n >= ISSUE_MIN]


def previous_issues():
    """어제 페이지의 이슈 키워드를 읽어 와서 새로 떠오른 단어를 표시하는 데 씁니다."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repo:
        return None
    owner, name = repo.split("/", 1)
    url = f"https://{owner.lower()}.github.io/{name}/issues.json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return set(json.loads(r.read().decode("utf-8")))
    except Exception:
        return None



# ---------- 비슷한 기사 묶기 ----------
SIMILARITY = 0.3        # 0~1. 높일수록 더 비슷해야 묶이고, 낮출수록 더 많이 묶입니다


def _core(title, remove):
    """비교용 제목: 회사명·괄호표시·기호를 빼고 띄어쓰기를 없앱니다."""
    t = re.sub(r"\[[^\]]*\]", "", title)          # [단독], [포토] 같은 머리표 제거
    for r in remove:
        t = t.replace(r, "")
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t).lower()


def _bigrams(t):
    return {t[k:k + 2] for k in range(len(t) - 1)}


def _similar(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / min(len(a), len(b))  # 짧은 제목 기준 겹침 비율


def cluster(items, remove):
    """같은 묶음 안의 기사들을 비슷한 것끼리 모읍니다. 최신 기사가 대표가 됩니다."""
    clusters = []
    for i in items:  # items 는 최신순
        bg = _bigrams(_core(i["title"], remove))
        best, best_sim = None, 0.0
        for c in clusters:
            sim = max(_similar(bg, x) for x in c["bigrams"])
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= SIMILARITY and len(bg) >= 4:
            best["items"].append(i)
            best["bigrams"].append(bg)
        else:
            clusters.append({"items": [i], "bigrams": [bg]})
    return clusters

# ---------- 페이지 만들기 ----------
def when_label(dt, now):
    if dt is None:
        return ""
    if dt.date() == now.date():
        return f"오늘 {dt:%H:%M}"
    if dt.date() == (now - timedelta(days=1)).date():
        return f"어제 {dt:%H:%M}"
    return f"{dt:%m.%d %H:%M}"


def naver(q):
    return f"https://search.naver.com/search.naver?where=news&sort=1&query={urllib.parse.quote(q)}"


def render(groups, items, issues, prev, errors):
    now = datetime.now(KST)
    days = "월화수목금토일"
    esc = html.escape

    def row(i):
        meta = []
        if i["source"]:
            meta.append(f"<span>{esc(i['source'])}</span>")
        w = when_label(i["dt"], now)
        if w:
            meta.append(f"<span>{w}</span>")
        return (f'<li data-title="{esc(i["title"])}"><a href="{esc(i["link"])}" target="_blank" rel="noopener">'
                f'<span class="title">{esc(i["title"])}</span>'
                f'<span class="meta">{"".join(meta)}</span></a></li>')

    def folder(c):
        first, rest = c["items"][0], c["items"][1:]
        sources = []
        for i in c["items"]:
            if i["source"] and i["source"] not in sources:
                sources.append(i["source"])
        src = ", ".join(sources[:2]) + (f" 외 {len(sources) - 2}곳" if len(sources) > 2 else "")
        w = when_label(first["dt"], now)
        all_titles = " ".join(i["title"] for i in c["items"])
        inner = "".join(row(i) for i in c["items"])
        return (f'<li class="cluster" data-title="{esc(all_titles)}"><details>'
                f'<summary><span class="title">{esc(first["title"])}</span>'
                f'<span class="meta"><span class="bundle">관련 기사 {len(c["items"])}건</span>'
                f'<span>{esc(src)}</span>{f"<span>{w}</span>" if w else ""}</span></summary>'
                f'<ul class="inner">{inner}</ul></details></li>')

    remove = [g["name"] for g in groups] + [w for g in groups for t in g["terms"] for w in t.split()]
    sections, buttons = [], [f'<button type="button" data-f="전체" aria-pressed="true">전체 {len(items)}</button>']
    for g in groups:
        gi = [i for i in items if i["group"] == g["name"]]
        clusters = cluster(gi, remove)
        buttons.append(f'<button type="button" data-f="{esc(g["name"])}" aria-pressed="false">{esc(g["name"])} {len(gi)}</button>')
        body = "".join(folder(c) if len(c["items"]) > 1 else row(c["items"][0]) for c in clusters) \
            or '<li class="empty">최근 48시간 새 기사 없음</li>'
        sections.append(f'<section class="group" data-tag="{esc(g["name"])}">'
                        f'<h3>{esc(g["name"])} <span class="count">{len(gi)}</span></h3>'
                        f'<ul class="news">{body}</ul></section>')

    if issues:
        chips = []
        for w, n in issues:
            new = ' <em class="new">NEW</em>' if prev is not None and w not in prev else ""
            chips.append(f'<button type="button" class="issue" data-w="{esc(w)}" aria-pressed="false">'
                         f'{esc(w)} <span class="n">{n}</span>{new}</button>')
        issue_html = "".join(chips)
    else:
        issue_html = '<p class="hint">아직 여러 기사에 반복해서 나온 단어가 없어요.</p>'

    chips = "".join(f'<a class="chip" target="_blank" rel="noopener" href="{naver(t)}">{esc(t)}</a>'
                    for g in groups for t in g["terms"])
    err_note = (f'<p class="warn">일부 검색어를 불러오지 못했어요({len(errors)}건). 다음 실행 때 다시 시도합니다.</p>'
                if errors else "")

    tpl = (BASE / "template.html").read_text(encoding="utf-8")
    return (tpl.replace("{{DATE_TITLE}}", f"{now.month}월 {now.day}일 {days[now.weekday()]}요일")
               .replace("{{UPDATED}}", f"{now:%Y.%m.%d %H:%M}")
               .replace("{{ISSUES}}", issue_html)
               .replace("{{FILTERS}}", "".join(buttons))
               .replace("{{ROWS}}", "\n".join(sections))
               .replace("{{CHIPS}}", chips)
               .replace("{{ERRORS}}", err_note))


def main():
    groups = read_groups()
    items, errors = collect(groups)
    for e in errors:
        print("경고:", e, file=sys.stderr)
    issues = issue_keywords(items, groups)
    prev = previous_issues()

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "index.html").write_text(render(groups, items, issues, prev, errors), encoding="utf-8")
    (OUT_DIR / "issues.json").write_text(json.dumps([w for w, _ in issues], ensure_ascii=False), encoding="utf-8")
    (OUT_DIR / "news.json").write_text(json.dumps(
        [{**i, "dt": i["dt"].isoformat() if i["dt"] else None} for i in items],
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"완료: 기사 {len(items)}건, 이슈 키워드 {len(issues)}개 → site/index.html")
    total_terms = sum(len(g["terms"]) for g in groups)
    if total_terms and len(errors) == total_terms:
        sys.exit(1)  # 전부 실패하면 기존 페이지를 덮어쓰지 않도록 실패 처리


if __name__ == "__main__":
    main()
