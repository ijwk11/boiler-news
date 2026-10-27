# 보일러 업계 아침 뉴스

매일 아침 6시 30분(한국시간)에 자동으로 보일러 업계 뉴스를 모아 웹페이지로 만들어 줍니다.
팀원들은 고정 주소 하나만 즐겨찾기해 두고 열면 됩니다. PC를 켜둘 필요가 없고 비용도 들지 않아요.

## 처음 한 번만 하는 설정 (약 10분)

1. https://github.com 에 가입하고 로그인합니다.
2. 오른쪽 위 `+` → **New repository**. 이름은 예를 들어 `boiler-news`, **Public** 선택 후 **Create repository**.
3. 만들어진 저장소 화면에서 **uploading an existing file** 링크를 누르고, 압축을 푼 폴더 안의 파일을 전부 끌어다 놓은 뒤 **Commit changes**.
   - `.github` 폴더는 숨김 폴더라 안 보일 수 있어요. 탐색기/Finder에서 숨김 파일 보기를 켜고 함께 올려주세요.
   - 올라간 뒤 저장소에 `.github/workflows/daily-news.yml` 파일이 보이면 성공입니다.
4. 저장소 **Settings** → 왼쪽 **Pages** → *Build and deployment*의 **Source**를 **GitHub Actions**로 바꿉니다.
5. 저장소 **Actions** 탭 → 왼쪽 **매일 아침 보일러 뉴스** → **Run workflow** 버튼으로 첫 실행을 합니다.
6. 1~2분 뒤 초록 체크가 뜨면 완료. 주소는 `https://<내 GitHub 아이디>.github.io/boiler-news/` 입니다. 이 주소를 팀원들에게 공유하세요.

이후로는 매일 아침 자동으로 갱신됩니다.

## 키워드 바꾸기

저장소에서 `keywords.txt`를 열고 연필(✏️) 아이콘으로 수정 → **Commit changes**. 다음 실행부터 반영됩니다.
특정 단어가 들어간 기사를 빼고 싶으면 `exclude.txt`에 같은 방식으로 적으면 됩니다.

## 알아두기

- 기사는 구글 뉴스 검색(RSS)에서 최근 48시간 기사를 가져옵니다. 제목을 누르면 원문 기사로 이동합니다.
- 무료 계정의 GitHub Pages 주소는 누구나 열어볼 수 있는 공개 페이지입니다(뉴스 제목과 링크만 담겨 있어요).
- GitHub 예약 실행은 서버 사정에 따라 수 분에서 수십 분 늦어질 수 있어요. 더 일찍 받고 싶으면
  `.github/workflows/daily-news.yml`의 `cron` 값을 앞당기세요(UTC 기준, 한국시간 - 9시간).
- 저장소에 60일 동안 아무 변경이 없으면 GitHub이 예약 실행을 멈출 수 있습니다. 메일 안내가 오면
  Actions 탭에서 다시 켜거나 키워드 파일을 한 번 수정해 주세요.
- 실행이 실패하면 기존 페이지가 그대로 남고, 저장소 주인에게 GitHub 알림 메일이 갑니다.

## 내 PC에서 시험해 보기 (선택)

파이썬 3.9 이상이 설치되어 있다면 폴더에서 `python fetch_news.py` 실행 → `site/index.html`을 브라우저로 열면 됩니다.
