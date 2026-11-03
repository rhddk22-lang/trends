# 연구 동향 아카이브

검색어를 등록해두면 매일 아침 7시에 뉴스와 논문을 자동으로 모아 날짜별 페이지로 쌓아주는 정적 사이트입니다. GitHub Pages에 올라가고, 검색엔진에는 노출되지 않도록 설정되어 있습니다.

---

## 1. 먼저 해야 할 일: `config.json` 채우기

이 파일 하나만 고치면 사이트 전체가 바뀝니다. 꼭 채워야 하는 곳은 세 군데입니다.

```jsonc
"site": {
  "title":    "연구 동향 아카이브",        // 사이트 이름
  "subtitle": "무엇을 모으는 곳인지 한 줄",
  "noindex":  true                        // true면 검색엔진에 노출되지 않음
},

"collect": {
  "news_keywords": ["다문화교육", "통일교육"],   // 매일 뉴스를 모을 검색어
  "korean":  { "queries": ["현대시 교육"], "window_days": 1095 },
  "english": { "queries": ["poetry education"], "window_days": 90 }
}
```

`owner` 블록은 푸터 한 줄에만 쓰입니다. 비워두면 아예 표시되지 않습니다.

### 왜 국문과 영문의 조건이 다른가

실제로 OpenAlex에 질의해본 결과입니다.

| 검색어 | 최근 45일 | 최근 2년 | 전체 |
|---|---|---|---|
| 현대시 교육 | 0 | 3 | 72 |
| 문학교육 | 0 | 27 | 473 |
| 북한이탈청소년 | 0 | 1 | 39 |
| poetry education | 115 | 2,338 | 15,572 |

국문 인문학 논문은 색인이 몇 달에서 1년 이상 늦게 들어오고 절대량도 적습니다. 영문은 정반대로 넘칩니다. 그래서 조건을 나눴습니다.

- **국문** — 기간 3년, 최신순, 최대 50편. 짧게 잡으면 0건이 됩니다.
- **영문** — 기간 90일, 관련도순, 최대 20편. 길게 잡으면 잡음에 묻힙니다.

같은 논문이 매번 다시 걸리는 것은 정상입니다. DOI와 제목으로 중복을 거르므로, 실제로 쌓이는 것은 **새로 색인된 것뿐**입니다. 그래서 국문의 첫 실행 때는 지난 3년치가 한 번에 들어오고, 이후에는 띄엄띄엄 몇 편씩 붙습니다.

### 검색어 요령

- 뉴스 검색어는 **한국어 그대로** 넣으면 됩니다. 너무 넓으면(`교육`) 잡음이 많고, 너무 좁으면 아무것도 안 걸립니다. 두세 단어 조합이 적당합니다.
- 논문은 **OpenAlex와 Crossref 두 곳**에 같은 검색어로 질의합니다. OpenAlex는 KCI 등재지 수록이 넓고, Crossref는 영문 국제 학술지 쪽이 강합니다.
- 각 목록은 5~15개면 충분합니다.
- 논문 페이지에 **어떤 검색어로 걸렸는지 태그가 붙습니다.** 쓸모없는 검색어를 골라내는 데 쓰세요.

### 비용

**전부 무료입니다. 결제 수단을 등록할 일이 없습니다.**

- GitHub Pages는 공개 저장소에서 무료입니다. 사이트 용량 상한은 1GB인데, 이 사이트는 텍스트뿐이라 몇 MB도 되지 않습니다.
- OpenAlex와 Crossref 모두 무료 공개 API입니다. 키도 필요 없습니다.

### 논문 수집 주기

논문은 **기본값이 주 1회(월요일)** 입니다. 뉴스는 매일 모읍니다.

국문 인문학 논문은 색인이 느리게 들어와 하루 단위로는 거의 변하지 않습니다. 매일 돌려봐야 같은 결과를 다시 받을 뿐이고, API 요청만 축냅니다. `config.json` 의 `papers_weekday` 로 바꿀 수 있습니다. `0`이 월요일, `6`이 일요일, `-1`이면 매일입니다.

수동 실행(Actions 탭의 Run workflow)과 설정 변경 시에는 요일과 무관하게 논문도 함께 모읍니다.

### OpenAlex API 키 (선택, 역시 무료)

키 없이도 동작합니다. 다만 키가 없으면 **같은 IP를 쓰는 사람들이 하루 100요청가량을 나눠 씁니다.** GitHub Actions는 IP를 널리 공유하므로 남들이 많이 쓴 날엔 걸릴 수 있습니다. 주 1회로 줄여둔 덕에 한 번에 40요청 정도라 대개 문제없지만, 로그에 "요청 한도에 걸렸습니다"가 반복되면 키를 받으세요.

**키는 무료이고 결제 정보를 요구하지 않습니다.** 표시되는 `$1/day` 는 요금이 아니라 요청 한도를 비용 단위로 환산한 숫자입니다.

1. <https://openalex.org/settings/api> 에서 키 발급
2. 저장소 → **Settings → Secrets and variables → Actions → New repository secret**
3. 이름 `OPENALEX_API_KEY`, 값에 키를 붙여넣기

워크플로가 알아서 집어 씁니다. **키를 `config.json` 에 적지 마세요.** 공개 저장소에 그대로 노출됩니다.

---

## 2. GitHub에 올리기

```bash
cd research-site
git init
git add .
git commit -m "첫 커밋"
git branch -M main
git remote add origin https://github.com/<사용자명>/<저장소명>.git
git push -u origin main
```

저장소는 **public으로 만드세요.** 무료 계정에서 private 저장소로 Pages를 쓰려면 유료 플랜이 필요합니다. 어차피 Pages 사이트 자체는 비공개가 되지 않으므로, 저장소를 public으로 두고 `noindex`로 검색 노출만 막는 편이 현실적입니다.

---

## 3. Pages 켜기

저장소 → **Settings → Pages** → *Build and deployment* 의 **Source** 를 `GitHub Actions` 로 바꿉니다. (`Deploy from a branch` 가 아닙니다.)

그다음 **Actions** 탭 → 왼쪽에서 `매일 동향 수집 및 배포` → **Run workflow** 를 눌러 한 번 수동 실행합니다. 2~3분 뒤 Pages 탭에 주소가 뜹니다.

이후에는 매일 아침 7시(한국시간)에 자동으로 돌아갑니다.

---

## 4. 검색 비노출에 대해

이 사이트는 두 가지 장치를 함께 씁니다.

- `robots.txt` 에 `Disallow: /`
- 모든 페이지 `<head>` 에 `noindex, nofollow, noarchive, nosnippet`

이러면 구글·네이버 등 정상적인 크롤러는 색인하지 않습니다. 다만 **이건 "검색에 안 뜸"이지 "비공개"가 아닙니다.** 주소를 아는 사람은 누구나 볼 수 있습니다. 진짜로 접근을 막으려면 GitHub Pages가 아니라 Vercel·Netlify의 비밀번호 보호나 Cloudflare Access를 써야 합니다.

검색에 노출시키고 싶어지면 `config.json` 의 `site.noindex` 를 `false` 로 바꾸면 됩니다.

---

## 5. 직접 돌려보기 (선택)

파이썬 3.12 이상만 있으면 됩니다. 설치할 패키지는 없습니다.

```bash
python3 scripts/collect.py --sample   # 네트워크 없이 예시 데이터 생성
python3 scripts/build.py              # _site/ 에 HTML 생성
python3 -m http.server -d _site 8000  # http://localhost:8000 에서 확인
```

실제 수집은 `--sample` 없이 실행합니다.

```bash
python3 scripts/collect.py            # 뉴스 매일 + 논문은 설정된 요일에만
python3 scripts/collect.py --papers   # 요일과 무관하게 논문도
python3 scripts/collect.py --news-only  # 뉴스만
```

---

## 구성

```
config.json              설정 — 평소에 고칠 파일은 이것뿐입니다
assets/style.css         디자인 (맨 위 색상 변수만 바꿔도 분위기가 달라집니다)
scripts/collect.py       수집기 — Google News RSS + Crossref
scripts/build.py         빌더 — JSON을 읽어 HTML 생성
data/trends/*.json       날짜별 수집 결과 (자동 생성·커밋)
data/studies.json        누적 논문 목록 (자동 생성·커밋)
.github/workflows/       매일 실행되는 자동화
_site/                   빌드 결과 (커밋하지 않음)
```

### 동작 방식

수집기는 검색어마다 Google News RSS를 읽어 기사를 모은 뒤, 제목이 비슷한 것들을 하나로 묶습니다. 같은 사건을 열 곳이 보도했다면 열 줄이 아니라 "10건 · ○○일보 외 9곳" 한 줄로 정리됩니다. 묶는 기준은 `config.json` 의 `cluster_threshold` 로 조절합니다. 값을 올리면 더 깐깐하게(덜 묶임), 내리면 더 느슨하게(많이 묶임) 묶입니다.

논문은 OpenAlex와 Crossref에서 가져옵니다. 두 곳에 같은 논문이 있는 경우가 많으므로 DOI로 먼저 거르고, DOI가 없으면 정규화한 제목으로 한 번 더 겁니다. 이렇게 걸러진 신규 논문만 `data/studies.json` 에 쌓입니다.

### 자주 하는 조정

| 하고 싶은 것 | 고칠 곳 |
|---|---|
| 실행 시각 변경 | `.github/workflows/daily.yml` 의 `cron` (UTC 기준) |
| 보관 기간 변경 | `config.json` 의 `collect.keep_days` |
| 묶음 민감도 | `config.json` 의 `collect.cluster_threshold` |
| 논문 수집 기간 | `config.json` 의 `collect.korean.window_days` / `collect.english.window_days` |
| 논문 편수 상한 | 같은 블록의 `max_results` |
| 논문 수집 요일 | `config.json` 의 `collect.papers_weekday` |
| 색상·글꼴 | `assets/style.css` 맨 위 `:root` 변수 |
| 메뉴 구성 | `config.json` 의 `nav` |
| 태그에서 뺄 단어 | `scripts/collect.py` 의 `STOPWORDS` |
