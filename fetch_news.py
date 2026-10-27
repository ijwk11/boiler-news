"""보일러 업계 아침 뉴스 페이지 생성기.

keywords.txt 의 키워드마다 구글 뉴스 RSS에서 최근 기사를 모아
site/index.html 한 장으로 만듭니다. 파이썬 기본 라이브러리만 사용합니다.

사용법:  python fetch_news.py
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

KST = timezone(timedelta(hours=9))
BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "site"

LOOKBACK_HOURS = 48     # 최근 몇 시간 이내 기사만 모을지
MAX_PER_KEYWORD = 15    # 키워드당 최대 기사 수
MAX_TOTAL = 60          # 페이지 전체 최대 기사 수


def read_list(name):
    p = BASE / name
    if not p.exists():
        return []
    lines = [l.strip() for l in p.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l and not l.startswith("#")]


def fetch_rss(keyword):
    q = urllib.parse.quote(f"{keyword} when:2d")
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (boiler-news-bot)"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def parse_items(xml_bytes, keyword):
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        source = (it.findtext("source") or "").strip()
        pub = it.findtext("pubDate")
        if not title or not link:
            continue
        # 구글 뉴스 제목은 "기사 제목 - 언론사" 형태라 뒤쪽 언론사명을 떼어냅니다.
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)].strip()
        try:
            dt = parsedate_to_datetime(pub).astimezone(KST) if pub else None
        except (TypeError, ValueError):
            dt = None
        items.append({"title": title, "link": link, "source": source, "dt": dt, "tag": keyword})
    return items


def norm(title):
    return re.sub(r"[\W_]+", "", title).lower()


def collect():
    keywords = read_list("keywords.txt")
    excludes = read_list("exclude.txt")
    cutoff = datetime.now(KST) - timedelta(hours=LOOKBACK_HOURS)
    seen, results, errors = set(), [], []

    for kw in keywords:
        try:
            items = parse_items(fetch_rss(kw), kw)
        except Exception as e:  # 한 키워드가 실패해도 나머지는 계속
            errors.append(f"{kw}: {e}")
            continue
        items = [i for i in items if i["dt"] is None or i["dt"] >= cutoff]
        items.sort(key=lambda i: i["dt"] or cutoff, reverse=True)
        count = 0
        for i in items:
            key = norm(i["title"])
            if key in seen or any(x in i["title"] for x in excludes):
                continue
            seen.add(key)
            results.append(i)
            count += 1
            if count >= MAX_PER_KEYWORD:
                break

    results.sort(key=lambda i: i["dt"] or cutoff, reverse=True)
    return keywords, results[:MAX_TOTAL], errors


def when_label(dt, now):
    if dt is None:
        return ""
    if dt.date() == now.date():
        return f"오늘 {dt:%H:%M}"
    if dt.date() == (now - timedelta(days=1)).date():
        return f"어제 {dt:%H:%M}"
    return f"{dt:%m.%d %H:%M}"


def render(keywords, items, errors):
    now = datetime.now(KST)
    days = "월화수목금토일"
    date_title = f"{now.month}월 {now.day}일 {days[now.weekday()]}요일"
    updated = f"{now:%Y.%m.%d %H:%M}"

    rows = []
    for i in items:
        meta = [f'<span class="tag">{html.escape(i["tag"])}</span>']
        if i["source"]:
            meta.append(f"<span>{html.escape(i['source'])}</span>")
        w = when_label(i["dt"], now)
        if w:
            meta.append(f"<span>{w}</span>")
        rows.append(
            f'<li data-tag="{html.escape(i["tag"])}"><a href="{html.escape(i["link"])}" target="_blank" rel="noopener">'
            f'<span class="title">{html.escape(i["title"])}</span>'
            f'<span class="meta">{"".join(meta)}</span></a></li>'
        )
    if not rows:
        rows.append('<li class="empty">최근 48시간 안에 새로 올라온 기사가 없어요. 아래 키워드 바로가기로 직접 찾아볼 수 있습니다.</li>')

    tags = [t for t in keywords if any(i["tag"] == t for i in items)]
    filter_btns = '<button type="button" data-f="전체" aria-pressed="true">전체 ' + str(len(items)) + "</button>" + "".join(
        f'<button type="button" data-f="{html.escape(t)}" aria-pressed="false">{html.escape(t)} '
        f'{sum(1 for i in items if i["tag"] == t)}</button>' for t in tags
    )
    chips = "".join(
        f'<a class="chip" target="_blank" rel="noopener" href="https://search.naver.com/search.naver?where=news&sort=1&query={urllib.parse.quote(k)}">{html.escape(k)}</a>'
        for k in keywords
    )
    err_note = ""
    if errors:
        err_note = f'<p class="warn">일부 키워드를 불러오지 못했어요({len(errors)}건). 다음 실행 때 다시 시도합니다.</p>'

    tpl = (BASE / "template.html").read_text(encoding="utf-8")
    return (tpl.replace("{{DATE_TITLE}}", date_title)
               .replace("{{UPDATED}}", updated)
               .replace("{{FILTERS}}", filter_btns)
               .replace("{{ROWS}}", "\n".join(rows))
               .replace("{{CHIPS}}", chips)
               .replace("{{ERRORS}}", err_note))


def main():
    keywords, items, errors = collect()
    for e in errors:
        print("경고:", e, file=sys.stderr)
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "index.html").write_text(render(keywords, items, errors), encoding="utf-8")
    (OUT_DIR / "news.json").write_text(json.dumps(
        [{**i, "dt": i["dt"].isoformat() if i["dt"] else None} for i in items],
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"완료: 기사 {len(items)}건 → site/index.html")
    if keywords and len(errors) == len(keywords):
        sys.exit(1)  # 전부 실패하면 기존 페이지를 덮어쓰지 않도록 실패 처리


if __name__ == "__main__":
    main()
