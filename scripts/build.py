#!/usr/bin/env python3
"""
정적 사이트 빌더 — config.json 과 data/ 를 읽어 _site/ 에 HTML을 만듭니다.

  python3 scripts/build.py

표준 라이브러리만 씁니다.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "_site"

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" '
    'href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@500;600;700&display=swap">'
    '<link rel="stylesheet" '
    'href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">'
)


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def squash(text: str) -> str:
    """띄어쓰기와 기호를 없애 '문학 교육' 과 '문학교육' 을 같게 봅니다."""
    return re.sub(r"[^\w가-힣]", "", (text or "").lower())


def assign_topics(haystack: str, topics: list[dict]) -> list[str]:
    """한 자료가 어느 주제에 들어가는지 고릅니다. 여러 개여도 됩니다."""
    hay = squash(haystack)
    return [t["label"] for t in topics
            if any(squash(term) in hay for term in t.get("terms", []))]


def topic_styles(topics: list[dict]) -> str:
    """주제마다 고유 색을 변수로 깔아둡니다. 밝은 화면과 어두운 화면 값이 따로입니다."""
    if not topics:
        return ""
    light = " ".join(
        f"--t{i}: {t.get('color', '#6E6A61')};" for i, t in enumerate(topics)
    )
    dark = " ".join(
        f"--t{i}: {t.get('colorDark', t.get('color', '#9B9589'))};"
        for i, t in enumerate(topics)
    )
    return (
        f"<style>:root {{ {light} }}\n"
        f"@media (prefers-color-scheme: dark) {{ :root:not([data-theme=\"light\"]) {{ {dark} }} }}\n"
        f":root[data-theme=\"dark\"] {{ {dark} }}</style>"
    )


def topic_index(topics: list[dict]) -> dict[str, int]:
    return {t["label"]: i for i, t in enumerate(topics)}


def topic_tags(labels: list[str], topics: list[dict]) -> str:
    """자료마다 붙는 작은 주제 딱지. 주제 색을 그대로 씁니다."""
    idx = topic_index(topics)
    return "".join(
        f'<span class="tag tag--topic" style="--c: var(--t{idx[label]})">{esc(label)}</span>'
        for label in labels if label in idx
    )


def topic_bar(counts: dict[str, int], total: int, topics: list[dict]) -> str:
    """위쪽 주제 버튼 줄. 자료가 하나도 없는 주제는 내보내지 않습니다."""
    live = [t["label"] for t in topics if counts.get(t["label"])]
    if not live:
        return ""
    idx = topic_index(topics)
    chips = ['<button class="chip chip--all is-on" data-topic="" type="button">'
             f'전체 <span class="chip__n">{total}</span></button>']
    for label in live:
        chips.append(
            f'<button class="chip" data-topic="{esc(label)}" type="button" '
            f'style="--c: var(--t{idx[label]})">'
            f'<span class="chip__dot"></span>{esc(label)} '
            f'<span class="chip__n">{counts[label]}</span></button>'
        )
    return (
        '<div class="topics" role="group" aria-label="주제 고르기">'
        + "".join(chips)
        + '</div><p class="topics__empty" hidden>이 주제에 해당하는 자료가 없습니다.</p>'
    )


TOPIC_SCRIPT = """<script>
(function () {
  var bar = document.querySelector('.topics');
  if (!bar) return;
  var items = Array.prototype.slice.call(document.querySelectorAll('[data-topics]'));
  var empty = document.querySelector('.topics__empty');
  bar.addEventListener('click', function (e) {
    var btn = e.target.closest('.chip');
    if (!btn) return;
    var pick = btn.getAttribute('data-topic');
    bar.querySelectorAll('.chip').forEach(function (c) {
      c.classList.toggle('is-on', c === btn);
    });
    var shown = 0;
    items.forEach(function (el) {
      var on = !pick || ('|' + el.getAttribute('data-topics') + '|').indexOf('|' + pick + '|') > -1;
      el.hidden = !on;
      if (on) shown++;
    });
    // 전부 숨겨진 구역은 제목까지 감춥니다.
    document.querySelectorAll('[data-group]').forEach(function (sec) {
      var any = sec.querySelector('[data-topics]:not([hidden])');
      sec.hidden = !any;
    });
    if (empty) empty.hidden = shown !== 0;
  });
})();
</script>"""


def load_config() -> dict:
    with (ROOT / "config.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def trend_days() -> list[dict]:
    folder = DATA / "trends"
    if not folder.exists():
        return []
    days = []
    for path in sorted(folder.glob("*.json"), reverse=True):
        payload = read_json(path, None)
        if payload and payload.get("clusters") is not None:
            payload.setdefault("date", path.stem)
            days.append(payload)
    return days


def pretty_date(stamp: str) -> str:
    try:
        parsed = datetime.strptime(stamp, "%Y-%m-%d")
    except ValueError:
        return stamp
    weekday = "월화수목금토일"[parsed.weekday()]
    return f"{parsed.year}년 {parsed.month}월 {parsed.day}일 ({weekday})"


# ──────────────────────────────────────────────────────────────
# 레이아웃
# ──────────────────────────────────────────────────────────────

def page(cfg: dict, *, depth: int, active: str, title: str, body: str,
         description: str = "") -> str:
    site = cfg["site"]
    up = "../" * depth or "./"
    robots = (
        '<meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex">'
        if site.get("noindex", True)
        else '<meta name="robots" content="index, follow">'
    )
    desc = description or site.get("description", "")

    current = ' aria-current="page"'
    nav = "".join(
        '<a href="{}{}/"{}>{}</a>'.format(
            up,
            esc(entry["path"]),
            current if entry["path"] == active else "",
            esc(entry["label"]),
        )
        for entry in cfg.get("nav", [])
    )

    owner = cfg.get("owner", {})
    owner_bits = []
    if owner.get("name"):
        owner_bits.append(f'<span>{esc(owner["name"])}</span>')
    if owner.get("note"):
        owner_bits.append(f'<span>{esc(owner["note"])}</span>')
    owner_links = "".join(
        f'<a href="{esc(link["url"])}" rel="noopener">{esc(link["label"])}</a>'
        for link in owner.get("links", [])
        if link.get("url")
    )
    if owner_links:
        owner_bits.append(f'<span class="footer__links">{owner_links}</span>')

    built = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")

    head_title = title if title == site.get("title") else f"{title} · {site.get('title','')}"

    return f"""<!doctype html>
<html lang="{esc(site.get('lang', 'ko'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{robots}
<title>{esc(head_title)}</title>
<meta name="description" content="{esc(desc)}">
{FONTS}
<link rel="stylesheet" href="{up}assets/style.css">
{topic_styles(cfg.get("collect", {}).get("topics", []))}
</head>
<body>
<div class="spectrum" aria-hidden="true"></div>
<header class="masthead">
  <div class="wrap">
    <p class="masthead__title"><a href="{up}">{esc(site.get('title', ''))}</a></p>
    {f'<p class="masthead__subtitle">{esc(site.get("subtitle", ""))}</p>' if site.get("subtitle") else ""}
    <div class="masthead__bar">
      <nav class="nav">{nav}</nav>
      <span class="masthead__stamp">updated {esc(built)}</span>
    </div>
  </div>
</header>
<main class="wrap">
{body}
</main>
<footer class="footer wrap">
{"".join(owner_bits) if owner_bits else '<span>자동 수집 아카이브</span>'}
</footer>
</body>
</html>
"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ──────────────────────────────────────────────────────────────
# 조각
# ──────────────────────────────────────────────────────────────

def render_cluster(cluster: dict, topics: list[dict] | None = None) -> str:
    sources = cluster.get("sources", [])
    count = cluster.get("count", 1)
    if count > 1 and sources:
        line = f"{esc(sources[0])} 외 {count - 1}곳"
    else:
        line = esc(cluster.get("lead_source", ""))

    locales = " · ".join(esc(loc) for loc in cluster.get("locales", []))

    marks = assign_topics(
        " ".join([cluster.get("title", "")] + cluster.get("keywords", [])
                 + cluster.get("tags", [])), topics or [])

    tags = topic_tags(marks, topics or []) + "".join(
        f'<span class="tag tag--quiet">{esc(tag)}</span>'
        for tag in cluster.get("tags", [])[:3]
    )

    lead_i = topic_index(topics or []).get(marks[0]) if marks else None
    badge_style = f' style="--c: var(--t{lead_i})"' if lead_i is not None else ''

    return f"""<li class="cluster" data-topics="{esc('|'.join(marks))}">
  <p class="cluster__title"><a href="{esc(cluster.get('url', '#'))}" rel="noopener nofollow" target="_blank">{esc(cluster.get('title', ''))}</a></p>
  <p class="cluster__meta">
    <span class="cluster__count"{badge_style}>{count}건</span>
    <span class="cluster__sources">{line}</span>
    {f'<span class="cluster__sources">· {locales}</span>' if locales else ''}
  </p>
  {f'<p class="cluster__tags">{tags}</p>' if tags else ''}
</li>"""


def render_entry(item: dict, topics: list[dict] | None = None) -> str:
    bits = []
    if item.get("authors"):
        bits.append(esc(", ".join(item["authors"])))
    if item.get("venue"):
        bits.append(f'<em>{esc(item["venue"])}</em>')
    if item.get("year"):
        bits.append(esc(item["year"]))
    meta = " · ".join(b for b in bits if b)

    # 한글 제목이 있으면 그것을 앞에 세우고 원제를 아래에 둡니다.
    original = esc(item.get("title", ""))
    korean = esc(item.get("title_ko", ""))
    url = item.get("url", "")
    shown = korean or original
    heading = (
        f'<a href="{esc(url)}" rel="noopener nofollow" target="_blank">{shown}</a>'
        if url else shown
    )
    sub = f'<p class="entry__original">{original}</p>' if korean else ""
    if item.get("title_ko_source") == "기계번역":
        sub = '<p class="entry__original"><span class="tag tag--warn">기계번역</span> ' \
              f'{original}</p>'

    marks = assign_topics(" ".join([
        item.get("title", ""), item.get("title_ko", ""),
        item.get("venue", ""), item.get("query", ""),
    ]), topics or [])

    chips = [topic_tags(marks, topics or [])]
    if item.get("query"):
        chips.append(f'<span class="tag tag--quiet">{esc(item["query"])}</span>')
    if item.get("source"):
        chips.append(f'<span class="tag tag--quiet">{esc(item["source"])}</span>')
    joined = "".join(chips)
    tags = f'<p class="cluster__tags">{joined}</p>' if joined else ""

    return f"""<li class="entry" data-topics="{esc('|'.join(marks))}">
  <p class="entry__title">{heading}</p>
  {sub}
  {f'<p class="entry__meta">{meta}</p>' if meta else ''}
  {f'<p class="entry__note">{esc(item.get("note",""))}</p>' if item.get("note") else ''}
  {tags}
</li>"""


def empty_box(message: str) -> str:
    return f'<p class="empty">{message}</p>'


def page_head(eyebrow: str, heading: str, note: str = "") -> str:
    return f"""<div class="page-head">
  <p class="page-head__eyebrow">{esc(eyebrow)}</p>
  <h1>{esc(heading)}</h1>
  {f'<p>{esc(note)}</p>' if note else ''}
</div>"""


# ──────────────────────────────────────────────────────────────
# 페이지
# ──────────────────────────────────────────────────────────────

def build_home(cfg: dict, days: list[dict], papers: dict) -> None:
    site = cfg["site"]
    parts: list[str] = []

    if days:
        latest = days[0]
        clusters = latest.get("clusters", [])
        parts.append(page_head(
            "오늘의 동향",
            pretty_date(latest["date"]),
            f"기사 {latest.get('articles', 0)}건을 {len(clusters)}개 묶음으로 정리했습니다.",
        ))
        top = "".join(render_cluster(c) for c in clusters[:6])
        parts.append(f"""<section class="section">
  <div class="section__head">
    <h2>주요 묶음</h2>
    <a class="section__more" href="trends/{esc(latest['date'])}/">이 날짜 전체 보기 →</a>
  </div>
  <ul class="cluster-list">{top or empty_box('이 날짜에 수집된 기사가 없습니다.')}</ul>
</section>""")
    else:
        parts.append(page_head("시작 전", site.get("title", ""), site.get("description", "")))
        parts.append(empty_box(
            "아직 수집된 동향이 없습니다. <code>config.json</code> 의 "
            "<code>collect.news_keywords</code> 를 채우고 "
            "<code>python3 scripts/collect.py</code> 를 실행하세요."
        ))

    if len(days) > 1:
        rows = "".join(
            f'<li><span class="archive__date">{esc(day["date"])}</span>'
            f'<a class="archive__label" href="trends/{esc(day["date"])}/">동향 기록</a>'
            f'<span class="archive__count">{len(day.get("clusters", []))}묶음</span></li>'
            for day in days[1:9]
        )
        parts.append(f"""<section class="section">
  <div class="section__head">
    <h2>최근 기록</h2>
    <a class="section__more" href="trends/">전체 보기 →</a>
  </div>
  <ul class="archive">{rows}</ul>
</section>""")

    items = papers.get("items", [])
    if items:
        rows = "".join(render_entry(item) for item in items[:4])
        parts.append(f"""<section class="section">
  <div class="section__head">
    <h2>새로 모은 논문</h2>
    <a class="section__more" href="studies/">전체 보기 →</a>
  </div>
  <ul class="entry-list">{rows}</ul>
</section>""")

    write(OUT / "index.html", page(
        cfg, depth=0, active="", title=site.get("title", ""), body="\n".join(parts)
    ))


def build_trends(cfg: dict, days: list[dict]) -> None:
    if days:
        rows = "".join(
            f'<li><span class="archive__date">{esc(day["date"])}</span>'
            f'<a class="archive__label" href="{esc(day["date"])}/">{pretty_date(day["date"])}</a>'
            f'<span class="archive__count">{len(day.get("clusters", []))}묶음</span></li>'
            for day in days
        )
        body = page_head("동향", "날짜별 기록", f"총 {len(days)}일치가 쌓여 있습니다.") + \
            f'<section class="section"><ul class="archive">{rows}</ul></section>'
    else:
        body = page_head("동향", "날짜별 기록") + empty_box("아직 기록이 없습니다.")

    write(OUT / "trends" / "index.html", page(
        cfg, depth=1, active="trends", title="동향", body=body
    ))

    topics = cfg.get("collect", {}).get("topics", [])
    for index, day in enumerate(days):
        clusters = day.get("clusters", [])
        listing = "".join(render_cluster(c, topics) for c in clusters)
        counts: dict[str, int] = {}
        for c in clusters:
            for label in assign_topics(
                " ".join([c.get("title", "")] + c.get("keywords", []) + c.get("tags", [])),
                topics,
            ):
                counts[label] = counts.get(label, 0) + 1
        nav_bits = []
        if index + 1 < len(days):
            nav_bits.append(f'<a class="section__more" href="../{esc(days[index + 1]["date"])}/">← 이전 날짜</a>')
        if index > 0:
            nav_bits.append(f'<a class="section__more" href="../{esc(days[index - 1]["date"])}/">다음 날짜 →</a>')

        body = page_head(
            "동향",
            pretty_date(day["date"]),
            f"기사 {day.get('articles', 0)}건 · {len(clusters)}개 묶음",
        ) + topic_bar(counts, len(clusters), topics) + f"""<section class="section">
  <ul class="cluster-list">{listing or empty_box('수집된 기사가 없습니다.')}</ul>
</section>
<p class="footer__links" style="margin:0;gap:1.2rem;">{"".join(nav_bits)}</p>""" + TOPIC_SCRIPT

        write(OUT / "trends" / day["date"] / "index.html", page(
            cfg, depth=2, active="trends", title=pretty_date(day["date"]), body=body
        ))


def build_studies(cfg: dict, papers: dict) -> None:
    items = papers.get("items", [])
    topics = cfg.get("collect", {}).get("topics", [])
    if items:
        counts: dict[str, int] = {}
        for item in items:
            for label in assign_topics(" ".join([
                item.get("title", ""), item.get("title_ko", ""),
                item.get("venue", ""), item.get("query", ""),
            ]), topics):
                counts[label] = counts.get(label, 0) + 1

        grouped: dict[str, list[dict]] = {}
        for item in items:
            grouped.setdefault(item.get("added", "기타"), []).append(item)

        sections = []
        for stamp in sorted(grouped, reverse=True):
            rows = "".join(render_entry(item, topics) for item in grouped[stamp])
            sections.append(f"""<section class="section" data-group="{esc(stamp)}">
  <div class="section__head"><h2>{esc(stamp)} 수집</h2>
  <span class="section__more">{len(grouped[stamp])}편</span></div>
  <ul class="entry-list">{rows}</ul>
</section>""")
        body = (
            page_head("논문", "자동 수집 논문", f"총 {len(items)}편")
            + topic_bar(counts, len(items), topics)
            + "\n".join(sections)
            + TOPIC_SCRIPT
        )
    else:
        body = page_head("논문", "자동 수집 논문") + empty_box(
            "아직 수집된 논문이 없습니다. <code>config.json</code> 의 "
            "<code>collect.paper_queries</code> 를 채우세요."
        )

    write(OUT / "studies" / "index.html", page(
        cfg, depth=1, active="studies", title="논문", body=body
    ))


def build_library(cfg: dict) -> None:
    library = cfg.get("library", {})
    groups = library.get("groups", [])
    sections = []
    for group in groups:
        rows = "".join(render_entry(item) for item in group.get("items", []))
        if not rows:
            continue
        sections.append(f"""<section class="section">
  <div class="section__head"><h2>{esc(group.get('heading', ''))}</h2></div>
  <ul class="entry-list">{rows}</ul>
</section>""")

    body = page_head("자료실", "직접 모은 자료", library.get("intro", ""))
    body += "\n".join(sections) if sections else empty_box(
        "아직 등록된 자료가 없습니다. <code>config.json</code> 의 <code>library.groups</code> 에 추가하세요."
    )

    write(OUT / "library" / "index.html", page(
        cfg, depth=1, active="library", title="자료실", body=body
    ))


# ──────────────────────────────────────────────────────────────

def main() -> int:
    cfg = load_config()

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    shutil.copytree(ROOT / "assets", OUT / "assets")

    days = trend_days()
    papers = read_json(DATA / "studies.json", {"items": []})

    build_home(cfg, days, papers)
    build_trends(cfg, days)
    build_studies(cfg, papers)
    build_library(cfg)

    if cfg["site"].get("noindex", True):
        (OUT / "robots.txt").write_text(
            "# 검색엔진 색인을 막습니다. 공개 접근을 막는 것은 아닙니다.\n"
            "User-agent: *\nDisallow: /\n",
            encoding="utf-8",
        )
    else:
        (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    # GitHub Pages 가 Jekyll 로 다시 처리하지 않도록 합니다.
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    pages = sum(1 for _ in OUT.rglob("*.html"))
    print(f"빌드 완료 — {pages}개 페이지, 동향 {len(days)}일치, 논문 {len(papers.get('items', []))}편")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
