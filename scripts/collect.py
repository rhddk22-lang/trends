#!/usr/bin/env python3
"""
동향 수집기 — 설정한 검색어로 뉴스와 논문을 모아 data/ 아래에 JSON으로 저장합니다.

  python3 scripts/collect.py              평소 실행 (오늘 날짜로 저장)
  python3 scripts/collect.py --date X     특정 날짜로 저장
  python3 scripts/collect.py --sample     네트워크 없이 예시 데이터 생성

표준 라이브러리만 씁니다. 설치할 패키지가 없습니다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
# 구글 뉴스는 서버에서 오는 요청을 503 으로 거부하는 일이 잦습니다.
# 평범한 브라우저처럼 보이는 머리말을 붙이면 대개 통과합니다.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}
TIMEOUT = 25

# 태그를 뽑을 때 버릴 단어들. 필요하면 자유롭게 늘리세요.
STOPWORDS = {
    "그리고", "그러나", "하지만", "위해", "통해", "대한", "관련", "이번", "지난", "올해",
    "대해", "라고", "에서", "으로", "하는", "했다", "한다", "있다", "없다", "것으로",
    "밝혔다", "전했다", "말했다", "기자", "단독", "속보", "종합", "영상", "포토",
    "the", "and", "for", "with", "from", "that", "this", "says", "said", "will",
    "has", "have", "its", "new", "amid", "over", "after", "into", "about", "more",
}


# ──────────────────────────────────────────────────────────────
# 공통
# ──────────────────────────────────────────────────────────────

def load_config() -> dict:
    with (ROOT / "config.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def fetch(url: str, attempts: int = 3) -> bytes | None:
    req = urllib.request.Request(url, headers=dict(BROWSER_HEADERS))
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429):
                # OpenAlex 는 키가 없으면 같은 IP 사용자들이 하루 한도를 나눠 씁니다.
                print(
                    f"  ! 요청 한도에 걸렸습니다 (HTTP {exc.code}). "
                    "OPENALEX_API_KEY 를 저장소 Secrets 에 넣으면 한도가 따로 잡힙니다. "
                    "키는 무료입니다.",
                    file=sys.stderr,
                )
                return None
            if exc.code >= 500 and attempt < attempts:
                time.sleep(2 * attempt)
                continue
            print(f"  ! 가져오기 실패 (HTTP {exc.code}): {url[:80]}", file=sys.stderr)
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt < attempts:
                time.sleep(2 * attempt)
                continue
            print(f"  ! 가져오기 실패: {exc}", file=sys.stderr)
            return None
    return None


def today(tz_offset_hours: int = 9) -> str:
    tz = timezone(timedelta(hours=tz_offset_hours))
    return datetime.now(tz).strftime("%Y-%m-%d")


# ──────────────────────────────────────────────────────────────
# 뉴스
# ──────────────────────────────────────────────────────────────

SOURCE_SUFFIX = re.compile(r"\s+[-–—]\s+[^-–—]{1,40}$")


def split_title(raw: str) -> tuple[str, str]:
    """구글 뉴스 제목은 보통 '제목 - 매체' 형태입니다."""
    raw = re.sub(r"\s+", " ", (raw or "").strip())
    match = SOURCE_SUFFIX.search(raw)
    if match:
        return raw[: match.start()].strip(), match.group(0).lstrip(" -–—").strip()
    return raw, ""


def normalize(text: str) -> str:
    text = re.sub(r"[^\w\s가-힣]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def google_news(keyword: str, locale: dict, limit: int) -> list[dict] | None:
    query = urllib.parse.quote_plus(f"{keyword} when:2d")
    url = (
        f"https://news.google.com/rss/search?q={query}"
        f"&hl={locale.get('hl', 'ko')}"
        f"&gl={locale.get('gl', 'KR')}"
        f"&ceid={locale.get('ceid', 'KR:ko')}"
    )
    raw = fetch(url)
    if not raw:
        return None
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        print(f"  ! RSS 해석 실패 ({keyword}): {exc}", file=sys.stderr)
        return None

    out: list[dict] = []
    for item in list(root.iterfind(".//item"))[:limit]:
        title_raw = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title_raw or not link:
            continue
        title, inline_source = split_title(title_raw)
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else inline_source
        out.append(
            {
                "title": title,
                "url": link,
                "source": source or inline_source or "출처 미상",
                "published": (item.findtext("pubDate") or "").strip(),
                "keyword": keyword,
                "locale": locale.get("label", locale.get("gl", "")),
            }
        )
    return out


def extract_tags(titles: list[str], limit: int = 4) -> list[str]:
    counts: Counter[str] = Counter()
    for title in titles:
        for word in normalize(title).split():
            if len(word) < 2 or word in STOPWORDS or word.isdigit():
                continue
            counts[word] += 1
    return [word for word, _ in counts.most_common(limit)]


def cluster_articles(articles: list[dict], threshold: float) -> list[dict]:
    """제목이 비슷한 기사들을 하나로 묶습니다."""
    buckets: list[dict] = []

    for article in articles:
        key = normalize(article["title"])
        if not key:
            continue
        placed = False
        for bucket in buckets:
            if SequenceMatcher(None, key, bucket["key"]).ratio() >= threshold:
                bucket["members"].append(article)
                placed = True
                break
        if not placed:
            buckets.append({"key": key, "members": [article]})

    clusters: list[dict] = []
    for bucket in buckets:
        members = bucket["members"]
        # 가장 중심에 가까운 제목을 대표로 고릅니다.
        if len(members) > 2:
            keys = [normalize(m["title"]) for m in members]
            scores = [
                sum(SequenceMatcher(None, k, other).ratio() for other in keys)
                for k in keys
            ]
            lead = members[scores.index(max(scores))]
        else:
            lead = min(members, key=lambda m: len(m["title"]))

        seen: list[str] = []
        for member in members:
            if member["source"] not in seen:
                seen.append(member["source"])

        clusters.append(
            {
                "title": lead["title"],
                "url": lead["url"],
                "lead_source": lead["source"],
                "count": len(members),
                "sources": seen,
                "locales": sorted({m["locale"] for m in members if m["locale"]}),
                "keywords": sorted({m["keyword"] for m in members}),
                "tags": extract_tags([m["title"] for m in members]),
            }
        )

    clusters.sort(key=lambda c: (-c["count"], c["title"]))
    return clusters


def collect_news(cfg: dict) -> dict:
    settings = cfg["collect"]
    keywords = [k for k in settings.get("news_keywords", []) if k.strip()]
    locales = settings.get("news_locales") or [{"label": "국내", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}]
    limit = int(settings.get("max_per_keyword", 30))

    articles: list[dict] = []
    seen_urls: set[str] = set()
    tried = 0
    failed = 0

    for keyword in keywords:
        for locale in locales:
            label = locale.get("label", locale.get("gl", ""))
            tried += 1
            found = google_news(keyword, locale, limit)
            if found is None:
                failed += 1
                print(f"  · 뉴스 · {keyword} ({label}) → 실패")
                time.sleep(2.0)
                continue
            fresh = 0
            for article in found:
                if article["url"] in seen_urls:
                    continue
                seen_urls.add(article["url"])
                articles.append(article)
                fresh += 1
            print(f"  · 뉴스 · {keyword} ({label}) → {fresh}건")
            time.sleep(0.8)  # 예의상 간격을 둡니다.

    clusters = cluster_articles(articles, float(settings.get("cluster_threshold", 0.62)))
    return {"articles": len(articles), "clusters": clusters,
            "tried": tried, "failed": failed}


# ──────────────────────────────────────────────────────────────
# 논문 (Crossref)
# ──────────────────────────────────────────────────────────────

def crossref(query: str, window_days: int, rows: int = 25) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%d")
    params = urllib.parse.urlencode(
        {
            "query.bibliographic": query,
            "filter": f"from-pub-date:{since},type:journal-article",
            "rows": rows,
            "sort": "published",
            "order": "desc",
            "select": "DOI,title,container-title,issued,author,URL,abstract",
        }
    )
    raw = fetch(f"https://api.crossref.org/works?{params}")
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []

    out: list[dict] = []
    for work in payload.get("message", {}).get("items", []):
        titles = work.get("title") or []
        if not titles:
            continue
        parts = (work.get("issued", {}).get("date-parts") or [[None]])[0]
        authors = [
            " ".join(filter(None, [a.get("given"), a.get("family")]))
            for a in (work.get("author") or [])[:4]
        ]
        container = work.get("container-title") or []
        out.append(
            {
                "title": re.sub(r"\s+", " ", titles[0]).strip(),
                "venue": container[0] if container else "",
                "year": str(parts[0]) if parts and parts[0] else "",
                "month": f"{parts[1]:02d}" if len(parts) > 1 and parts[1] else "",
                "authors": [a for a in authors if a],
                "doi": (work.get("DOI") or "").lower(),
                "url": work.get("URL", ""),
                "query": query,
                "lang": "",
                "source": "Crossref",
            }
        )
    return out


def openalex(query: str, window_days: int, rows: int = 25,
             sort: str = "publication_date:desc") -> list[dict]:
    """
    OpenAlex. 국내 인문·교육 학술지 수록률이 Crossref보다 훨씬 넓고,
    한글 검색어도 그대로 통합니다. API 키 없이도 동작합니다.

    주의: 국문 인문학 논문은 OpenAlex 색인이 몇 달에서 1년 이상 늦게 들어오고
    절대량도 적습니다. 그래서 국문 검색어는 기간을 길게 잡아야 합니다.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%d")
    encoded = urllib.parse.quote(query, safe="")
    url = (
        "https://api.openalex.org/works"
        f"?filter=title_and_abstract.search:{encoded},from_publication_date:{since}"
        f"&per-page={rows}&sort={sort}"
    )
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if api_key:
        url += f"&api_key={urllib.parse.quote(api_key, safe='')}"

    raw = fetch(url)
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []

    out: list[dict] = []
    for work in payload.get("results", []):
        title = (work.get("display_name") or "").strip()
        if not title:
            continue
        location = work.get("primary_location") or {}
        venue_source = location.get("source") or {}
        authors = [
            (a.get("author") or {}).get("display_name", "")
            for a in (work.get("authorships") or [])[:4]
        ]
        doi = (work.get("doi") or "").replace("https://doi.org/", "").lower()
        landing = location.get("landing_page_url") or work.get("doi") or work.get("id", "")
        out.append(
            {
                "title": re.sub(r"\s+", " ", title),
                "venue": venue_source.get("display_name", "") or "",
                "year": str(work.get("publication_year") or ""),
                "month": (work.get("publication_date") or "")[5:7],
                "authors": [a for a in authors if a],
                "doi": doi,
                "url": landing,
                "query": query,
                "lang": work.get("language", "") or "",
                "source": "OpenAlex",
            }
        )
    return out


def paper_key(paper: dict) -> str:
    """DOI가 있으면 DOI로, 없으면 정규화한 제목으로 중복을 거릅니다."""
    doi = (paper.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    return f"title:{normalize(paper.get('title', ''))}"


HANGUL = re.compile(r"[가-힣]")


def crossref_original_titles(dois: list[str], batch: int = 20) -> dict[str, str]:
    """
    국내 학술지 논문은 KCI에 영문 제목으로 등록되는 경우가 많지만,
    Crossref 의 original-title 필드에 한글 원제가 함께 들어 있습니다.
    기계번역보다 이쪽이 정확하므로 먼저 시도합니다.
    """
    found: dict[str, str] = {}
    for i in range(0, len(dois), batch):
        chunk = [d for d in dois[i:i + batch] if d]
        if not chunk:
            continue
        flt = ",".join(f"doi:{d}" for d in chunk)
        url = (
            "https://api.crossref.org/works?"
            + urllib.parse.urlencode(
                {"filter": flt, "rows": batch, "select": "DOI,original-title"}
            )
        )
        raw = fetch(url)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for work in payload.get("message", {}).get("items", []):
            titles = work.get("original-title") or []
            if titles and HANGUL.search(titles[0]):
                found[(work.get("DOI") or "").lower()] = re.sub(r"\s+", " ", titles[0]).strip()
        time.sleep(0.3)
    return found


def crossref_months(dois: list[str], batch: int = 20) -> dict[str, str]:
    """DOI 묶음으로 발행 월을 받아옵니다. Crossref 의 issued 에 연·월·일이 들어 있습니다."""
    found: dict[str, str] = {}
    for i in range(0, len(dois), batch):
        chunk = [d for d in dois[i:i + batch] if d]
        if not chunk:
            continue
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode({
            "filter": ",".join(f"doi:{d}" for d in chunk),
            "rows": batch,
            "select": "DOI,issued",
        })
        raw = fetch(url)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for work in payload.get("message", {}).get("items", []):
            parts = (work.get("issued", {}).get("date-parts") or [[None]])[0]
            if len(parts) > 1 and parts[1]:
                found[(work.get("DOI") or "").lower()] = f"{int(parts[1]):02d}"
        time.sleep(0.3)
    return found


def add_months(items: list[dict]) -> dict:
    """
    월이 비어 있는 항목만 채웁니다. 이미 채워진 것은 건드리지 않으므로
    매일 돌려도 새로 들어온 것만 처리합니다.
    """
    todo = [it for it in items if not it.get("month") and it.get("doi")]
    if not todo:
        return {"filled": 0, "remaining": 0}

    found = crossref_months([it["doi"] for it in todo])
    n = 0
    for it in todo:
        hit = found.get((it.get("doi") or "").lower())
        if hit:
            it["month"] = hit
            n += 1

    remaining = len([x for x in items if not x.get("month")])
    return {"filled": n, "remaining": remaining}


def machine_translate(text: str) -> str:
    """
    MyMemory 무료 번역. 키가 필요 없습니다.
    익명으로 쓰면 하루 한도가 낮고 같은 IP 를 쓰는 사람들과 나눠 쓰므로,
    MYMEMORY_EMAIL 을 저장소 Secrets 에 넣어두면 한도가 열 배로 늘어납니다.
    """
    params = {"q": text[:480], "langpair": "en|ko"}
    email = os.environ.get("MYMEMORY_EMAIL", "").strip()
    if email:
        params["de"] = email
    url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode(params)
    raw = fetch(url, attempts=1)
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if payload.get("responseStatus") != 200:
        return ""
    out = (payload.get("responseData") or {}).get("translatedText", "").strip()
    # 한도를 넘기면 안내 문구를 본문처럼 돌려주므로 걸러냅니다.
    if not out or "MYMEMORY WARNING" in out.upper() or not HANGUL.search(out):
        return ""
    return out


def add_korean_titles(items: list[dict], budget: int) -> dict:
    """
    한글 제목을 붙입니다. title_ko 가 이미 있는 항목은 건드리지 않으므로
    매일 돌려도 새로 들어온 것만 처리합니다.
    """
    todo = [
        it for it in items
        if not it.get("title_ko") and not HANGUL.search(it.get("title", ""))
    ]
    if not todo:
        return {"original": 0, "translated": 0, "remaining": 0}

    # 1단계 — Crossref 에서 한글 원제 찾기
    originals = crossref_original_titles([it.get("doi", "") for it in todo if it.get("doi")])
    n_orig = 0
    for it in todo:
        hit = originals.get((it.get("doi") or "").lower())
        if hit:
            it["title_ko"] = hit
            it["title_ko_source"] = "원제"
            n_orig += 1

    # 2단계 — 남은 것은 기계번역. 하루 한도가 있어 예산만큼만 합니다.
    rest = [it for it in todo if not it.get("title_ko")]
    n_trans = 0
    misses = 0
    for it in rest[:budget]:
        ko = machine_translate(it.get("title", ""))
        if not ko:
            misses += 1
            # 한 번 걸러진 것은 넘어가되, 연달아 실패하면 한도로 보고 멈춥니다.
            if misses >= 3:
                print("  ! 번역 한도에 걸린 듯합니다. 남은 것은 다음 실행으로 넘깁니다.",
                      file=sys.stderr)
                break
            time.sleep(1.5)
            continue
        misses = 0
        it["title_ko"] = ko
        it["title_ko_source"] = "기계번역"
        n_trans += 1
        time.sleep(0.6)

    remaining = len([it for it in items
                     if not it.get("title_ko") and not HANGUL.search(it.get("title", ""))])
    return {"original": n_orig, "translated": n_trans, "remaining": remaining}


def squash(text: str) -> str:
    """띄어쓰기와 기호를 없앱니다. '문학 교육' 과 '문학교육' 을 같게 보기 위해서입니다."""
    return re.sub(r"[^\w가-힣]", "", (text or "").lower())


def is_relevant(item: dict, terms: list[str]) -> bool:
    """
    OpenAlex 는 한글 다어절 검색어를 느슨하게 처리합니다.
    '이주배경 학생 교육' 이 '학생' 이나 '교육' 만 있어도 걸리는 식이라
    제목에 핵심어가 실제로 들어 있는지 한 번 더 확인합니다.
    """
    if not terms:
        return True
    hay = squash(item.get("title", "")) + " " + squash(item.get("title_ko", "")) \
        + " " + squash(item.get("venue", ""))
    return any(squash(t) in hay for t in terms)


def collect_papers(cfg: dict, stamp: str) -> dict:
    """
    국문과 영문은 사정이 정반대라 조건을 나눠 겁니다.

      국문 — 색인이 느리고 양이 적음  → 기간을 길게, 최신순으로
      영문 — 양이 넘침               → 기간을 짧게, 관련도순으로

    같은 논문이 매번 다시 걸리는 것은 정상입니다. 중복은 걸러지고
    새로 색인된 것만 쌓입니다.
    """
    settings = cfg["collect"]
    ko = settings.get("korean", {})
    en = settings.get("english", {})

    groups = [
        {
            "label": "국문",
            "queries": [q for q in ko.get("queries", []) if q.strip()],
            "window": int(ko.get("window_days", 1095)),
            "rows": int(ko.get("max_results", 50)),
            "sort": ko.get("sort", "publication_date:desc"),
        },
        {
            "label": "영문",
            "queries": [q for q in en.get("queries", []) if q.strip()],
            "window": int(en.get("window_days", 90)),
            "rows": int(en.get("max_results", 20)),
            "sort": en.get("sort", "relevance_score:desc"),
        },
    ]

    store_path = DATA / "studies.json"
    store = {"updated": "", "items": []}
    if store_path.exists():
        try:
            store = json.loads(store_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    known = {paper_key(item) for item in store.get("items", [])}
    fresh: list[dict] = []

    for group in groups:
        for query in group["queries"]:
            found = openalex(query, group["window"], group["rows"], group["sort"])
            time.sleep(0.4)
            found += crossref(query, group["window"], group["rows"])
            time.sleep(0.4)

            added_here = 0
            for paper in found:
                key = paper_key(paper)
                if key in known:
                    continue
                known.add(key)
                paper["added"] = stamp
                paper["group"] = group["label"]
                fresh.append(paper)
                added_here += 1
            print(f"  · 논문 · [{group['label']}] {query} → 신규 {added_here}편")

    items = (fresh + store.get("items", []))[:900]

    # 한글 제목을 먼저 붙입니다. 걸러낼 때 한글 원제도 함께 보기 위해서입니다.
    budget = int(settings.get("translate_per_run", 120))
    titles = add_korean_titles(items, budget)
    print(
        f"  → 한글 제목: 원제 {titles['original']}건, 번역 {titles['translated']}건"
        + (f", 남은 것 {titles['remaining']}건은 다음 실행에서" if titles["remaining"] else "")
    )

    months = add_months(items)
    if months["filled"]:
        print(f"  → 발행 월 {months['filled']}건을 채웠습니다."
              + (f" (아직 없는 것 {months['remaining']}건)" if months["remaining"] else ""))

    terms = settings.get("relevance_terms", [])
    before = len(items)
    items = [it for it in items if is_relevant(it, terms)]
    if before != len(items):
        print(f"  → 주제와 무관한 {before - len(items)}편을 걸러냈습니다. (남은 {len(items)}편)")

    store = {"updated": stamp, "items": items[:800]}
    store_path.write_text(
        json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"new": len(fresh), "total": len(items), "titles": titles}


# ──────────────────────────────────────────────────────────────
# 예시 데이터
# ──────────────────────────────────────────────────────────────

def write_sample(stamp: str) -> None:
    (DATA / "trends").mkdir(parents=True, exist_ok=True)
    clusters = [
        {
            "title": "예시 · 묶음 기사 제목이 여기에 들어갑니다",
            "url": "https://example.com/1",
            "lead_source": "예시일보",
            "count": 7,
            "sources": ["예시일보", "샘플신문", "테스트방송"],
            "locales": ["국내", "해외"],
            "keywords": ["검색어1"],
            "tags": ["예시", "태그", "자동추출"],
        },
        {
            "title": "예시 · 두 번째 묶음, 해외 보도가 함께 묶인 경우",
            "url": "https://example.com/2",
            "lead_source": "Sample Times",
            "count": 3,
            "sources": ["Sample Times", "Demo Post"],
            "locales": ["해외"],
            "keywords": ["검색어2"],
            "tags": ["sample", "demo"],
        },
        {
            "title": "예시 · 단독 보도 하나만 잡힌 경우",
            "url": "https://example.com/3",
            "lead_source": "테스트뉴스",
            "count": 1,
            "sources": ["테스트뉴스"],
            "locales": ["국내"],
            "keywords": ["검색어3"],
            "tags": ["단일"],
        },
    ]
    (DATA / "trends" / f"{stamp}.json").write_text(
        json.dumps(
            {"date": stamp, "generated_at": stamp, "articles": 11, "clusters": clusters},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (DATA / "studies.json").write_text(
        json.dumps(
            {
                "updated": stamp,
                "items": [
                    {
                        "title": "Example article title collected from Crossref",
                        "venue": "Journal of Examples",
                        "year": "2026",
                        "authors": ["Jane Doe", "John Roe"],
                        "doi": "10.0000/example.1",
                        "url": "https://doi.org/10.0000/example.1",
                        "query": "your research topic",
                        "added": stamp,
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"예시 데이터를 만들었습니다 ({stamp}).")


# ──────────────────────────────────────────────────────────────

def prune(keep_days: int) -> None:
    folder = DATA / "trends"
    if not folder.exists():
        return
    files = sorted(folder.glob("*.json"), reverse=True)
    for stale in files[keep_days:]:
        stale.unlink()


def papers_due(cfg: dict, stamp: str) -> bool:
    """
    논문은 매일 돌릴 필요가 없습니다. 국문 인문학 논문은 색인이 느리게 들어와
    하루 단위로는 거의 변하지 않고, 매일 돌리면 OpenAlex 요청만 축냅니다.
    기본값은 주 1회(월요일)입니다. papers_weekday 를 -1 로 두면 매일 돕니다.
    """
    weekday = int(cfg["collect"].get("papers_weekday", 0))
    if weekday < 0:
        return True
    try:
        return datetime.strptime(stamp, "%Y-%m-%d").weekday() == weekday
    except ValueError:
        return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="저장할 날짜 (YYYY-MM-DD)")
    parser.add_argument("--sample", action="store_true", help="네트워크 없이 예시 데이터 생성")
    parser.add_argument("--papers", action="store_true", help="요일과 무관하게 논문도 수집")
    parser.add_argument("--news-only", action="store_true", help="뉴스만 수집")
    args = parser.parse_args()

    cfg = load_config()
    stamp = args.date or today()

    if args.sample:
        write_sample(stamp)
        return 0

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "trends").mkdir(parents=True, exist_ok=True)

    print(f"[{stamp}] 수집 시작")
    news = collect_news(cfg)

    # 전부 실패했는데 빈 파일을 쓰면 그날이 '기사 0건' 으로 박제됩니다.
    # 차라리 쓰지 않고 넘어가면 다음 실행이나 다음 날 채워집니다.
    if news["articles"] == 0 and news["failed"] > 0:
        print(
            f"  ! 뉴스 {news['tried']}건 중 {news['failed']}건이 실패하고 기사가 하나도 "
            "없어 오늘 파일을 쓰지 않습니다. 기존 기록은 그대로 둡니다.",
            file=sys.stderr,
        )
    else:
        (DATA / "trends" / f"{stamp}.json").write_text(
            json.dumps(
                {
                    "date": stamp,
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "articles": news["articles"],
                    "clusters": news["clusters"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        note = f" ({news['failed']}건 실패)" if news["failed"] else ""
        print(f"  → 기사 {news['articles']}건을 {len(news['clusters'])}개로 묶었습니다.{note}")

    if args.news_only:
        print("  · 논문 수집 건너뜀 (--news-only)")
    elif args.papers or papers_due(cfg, stamp):
        papers = collect_papers(cfg, stamp)
        print(f"  → 논문 신규 {papers['new']}편 (누적 {papers['total']}편)")
    else:
        weekday_name = "월화수목금토일"[int(cfg["collect"].get("papers_weekday", 0))]
        print(f"  · 논문 수집은 {weekday_name}요일에만 돕니다. 지금 돌리려면 --papers")

    prune(int(cfg["collect"].get("keep_days", 400)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
