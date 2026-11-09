#!/usr/bin/env python3
"""
선행연구 지도 — data/studies.json 을 읽어 _site/map/index.html 을 만듭니다.

scripts/build.py 가 _site/ 를 만든 다음에 실행해야 합니다.
  python3 scripts/build.py && python3 scripts/review_map.py

무엇을 하느냐면, 모아둔 논문을 네 영역으로 나누고 그중 몇 편이 실제로
문학 텍스트를 다루는지 세어 그림 두 장과 표로 보여줍니다. 숫자는 모두
수집된 데이터에서 그때그때 계산하므로 논문이 늘면 같이 움직입니다.
손으로 고른 논문 목록만 data/map_picks.txt 에서 따로 읽습니다.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build import OUT, ROOT, esc, load_config, page, read_json, write  # noqa: E402


# ──────────────────────────────────────────────────────────────
# 분류 규칙
# ──────────────────────────────────────────────────────────────
# 영역은 수집 검색어로 가릅니다. config.json 의 검색어를 바꾸면
# 여기도 같이 손봐야 합니다.
AREAS: list[tuple[str, set[str]]] = [
    ("다문화·상호문화교육", {
        "다문화교육", "다문화 문학교육", "상호문화 교육",
        "이주배경 학생 교육", "환대 교육",
    }),
    ("문학교육·국어과 교육과정", {"문학교육", "국어과 교육과정"}),
    ("통일교육·북한이탈", {"통일교육", "북한이탈주민 교육", "북한이탈청소년"}),
    ("현대시·시교육", {
        "현대시 교육", "시 텍스트 교육", "시 창작 교육", "시 감상 교육",
    }),
]

# 제목에 이 말이 있으면 문학 텍스트를 다룬 것으로 봅니다.
# '시' 한 글자는 쓰지 않습니다. '리터러시'나 '특별시교육청'까지 걸립니다.
LIT_WORDS = [
    "문학", "현대시", "시 창작", "시 감상", "시 비평", "시 낭송", "시 텍스트",
    "시 그림책", "시 읽기", "시 쓰기", "시집", "서시", "디카시", "포엠", "시인",
    "소설", "동화", "그림책", "설화", "신화", "희곡", "수필", "웹툰", "영화",
    "서사", "스토리텔링",
]

# '인문학' 의 '문학' 은 세지 않습니다.
LIT_TRAPS = ["인문학"]

LIT_WORDS_EN = [
    "poetry", "poem", "poet", "literary", "literature", "novel",
    "fiction", "narrative", "story", "drama", "film", "verse",
]

# 상호문화 쪽을 향한 논문인지 보는 말입니다.
INTERCULTURAL_WORDS = [
    "상호문화", "타자", "환대", "다문화", "이주", "외국인", "유학생",
    "북한이탈", "통일",
]


def title_of(item: dict) -> str:
    # 수집된 제목에 &lt; 같은 문자 참조가 섞여 들어오는 경우가 있어 한 번 풀어줍니다.
    return html.unescape(item.get("title_ko") or item.get("title") or "")


def is_literary(item: dict) -> bool:
    text = title_of(item)
    for trap in LIT_TRAPS:
        text = text.replace(trap, "")
    if item.get("group") == "영문":
        low = item.get("title", "").lower()
        return any(word in low for word in LIT_WORDS_EN)
    return any(word in text for word in LIT_WORDS)


def is_intercultural(item: dict) -> bool:
    return any(word in title_of(item) for word in INTERCULTURAL_WORDS)


def doi_key(value: str) -> str:
    """DOI 를 비교할 수 있는 형태로 다듬습니다."""
    text = (value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/",
                   "http://dx.doi.org/", "https://dx.doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.rstrip("/")


# ──────────────────────────────────────────────────────────────
# 손으로 고른 목록
# ──────────────────────────────────────────────────────────────

def load_picks() -> list[tuple[str, str, str]]:
    path = ROOT / "data" / "map_picks.txt"
    if not path.exists():
        return []
    picks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [bit.strip() for bit in line.split("|")]
        if len(parts) < 2 or not parts[1]:
            continue
        group = parts[0]
        key = parts[1]
        note = parts[2] if len(parts) > 2 else ""
        picks.append((group, key, note))
    return picks


def index_items(items: list[dict]) -> dict[str, dict]:
    table: dict[str, dict] = {}
    for item in items:
        if item.get("doi"):
            table[doi_key(item["doi"])] = item
        if item.get("url"):
            table[doi_key(item["url"])] = item
    return table


# ──────────────────────────────────────────────────────────────
# 그림
# ──────────────────────────────────────────────────────────────

def bar_chart(rows: list[tuple[str, int, int]]) -> str:
    """영역별 전체 편수와 그중 문학 텍스트를 다룬 편수."""
    if not rows:
        return ""
    peak = max(total for _, total, _ in rows) or 1
    left, span, y0, step, height = 196, 376, 104, 52, 26
    body = []
    for index, (name, total, lit) in enumerate(rows):
        y = y0 + index * step
        full = total / peak * span
        part = lit / peak * span
        share = round(lit / total * 100) if total else 0
        body.append(f"""
  <g>
    <text x="{left - 12}" y="{y + 18}" text-anchor="end" fill="var(--ink)">{esc(name)}</text>
    <rect x="{left}" y="{y}" width="{full:.1f}" height="{height}" rx="3" fill="var(--line)"/>
    <rect x="{left}" y="{y}" width="{part:.1f}" height="{height}" rx="3" fill="var(--accent)"/>
    <text x="{left + full + 10:.1f}" y="{y + 18}" fill="var(--ink-soft)">{total}편 중 {lit}편 ({share}%)</text>
  </g>""")
    total_h = y0 + len(rows) * step + 34
    return f"""<figure class="map-figure">
<svg viewBox="0 0 760 {total_h}" role="img" aria-label="영역별 전체 편수와 그중 문학 텍스트를 다룬 편수" font-size="13">
  <text x="20" y="30" font-size="16" font-weight="600" fill="var(--ink)">다문화와 통일 영역은 두꺼운데 문학이 없다</text>
  <text x="20" y="52" font-size="12" fill="var(--muted)">국문 논문을 수집 검색어에 따라 네 영역으로 나눈 것입니다.</text>
  <g>
    <rect x="196" y="68" width="12" height="12" rx="2" fill="var(--line)"/>
    <text x="214" y="79" font-size="12" fill="var(--muted)">전체</text>
    <rect x="300" y="68" width="12" height="12" rx="2" fill="var(--accent)"/>
    <text x="318" y="79" font-size="12" fill="var(--muted)">문학 텍스트</text>
  </g>{"".join(body)}
  <text x="20" y="{total_h - 10}" font-size="12" fill="var(--faint)">문학 텍스트 기준은 제목에 문학·현대시·소설·설화·그림책·영화 같은 장르어가 있는 논문입니다.</text>
</svg>
</figure>"""


def quadrant(narrative_lit: int, narrative_main: int,
             poetry_inter: int, poetry_main: int) -> str:
    """다루는 텍스트 × 교육 목표."""
    cells = [
        (450, 112, "현대시 × 상호문화", poetry_inter, "가장 얇은 칸", True),
        (196, 112, "다문화 문학교육", narrative_lit, "설화 · 전래동화 · 그림책 · 영화", False),
        (450, 268, "현대시교육", poetry_main, "AI · 디지털이 절반", False),
        (196, 268, "문학교육 주류", narrative_main, "공감 · 돌봄 · 타자 이해 · 위치성", False),
    ]
    blocks = []
    for x, y, name, count, note, hot in cells:
        fill = 'fill="var(--accent-bg)"' if hot else 'fill="var(--surface)"'
        stroke = "var(--accent)" if hot else "var(--line)"
        width = "2" if hot else "1.25"
        blocks.append(f"""
  <g>
    <rect x="{x}" y="{y}" width="248" height="148" rx="8" {fill} stroke="{stroke}" stroke-width="{width}"/>
    <text x="{x + 16}" y="{y + 30}" font-size="14" font-weight="600" fill="var(--ink)">{esc(name)}</text>
    <text x="{x + 16}" y="{y + 56}" fill="var(--ink)">{count}편</text>
    <text x="{x + 16}" y="{y + 82}" font-size="12" fill="var(--muted)">{esc(note)}</text>
  </g>""")
    return f"""<figure class="map-figure">
<svg viewBox="0 0 760 468" role="img" aria-label="다루는 텍스트와 교육 목표로 나눈 네 칸" font-size="13">
  <text x="20" y="30" font-size="16" font-weight="600" fill="var(--ink)">현대시와 상호문화가 만나는 칸이 가장 얇다</text>
  <text x="20" y="52" font-size="12" fill="var(--muted)">문학 텍스트를 다룬 국문 논문만 네 칸으로 나눈 것입니다.</text>
  <text x="20" y="84" font-size="12" fill="var(--faint)">교육 목표 ↑</text>{"".join(blocks)}
  <text x="184" y="190" text-anchor="end" font-size="12" fill="var(--muted)">상호문화 · 타자 이해</text>
  <text x="184" y="346" text-anchor="end" font-size="12" fill="var(--muted)">문학 역량</text>
  <text x="320" y="440" text-anchor="middle" font-size="12" fill="var(--muted)">서사 장르</text>
  <text x="574" y="440" text-anchor="middle" font-size="12" fill="var(--muted)">현대시</text>
  <text x="447" y="462" text-anchor="middle" font-size="12" fill="var(--faint)">다루는 텍스트 →</text>
</svg>
</figure>"""


# ──────────────────────────────────────────────────────────────
# 표
# ──────────────────────────────────────────────────────────────

def paper_rows(items: list[dict], note_of=None) -> str:
    rows = []
    for item in items:
        title = esc(title_of(item))
        url = item.get("url", "")
        link = f'<a href="{esc(url)}" rel="noopener">{title}</a>' if url else title
        if item.get("title_ko_source") == "기계번역":
            link += ' <span class="tag tag--warn">기계번역</span>'
        note = note_of(item) if note_of else esc(item.get("venue", ""))
        rows.append(f"""<tr>
  <td class="map-table__year">{esc(item.get("year", ""))}</td>
  <td>{link}</td>
  <td class="map-table__note">{note}</td>
</tr>""")
    return "".join(rows)


def paper_table(items: list[dict], third: str, note_of=None) -> str:
    if not items:
        return '<p class="empty">아직 해당하는 논문이 없습니다.</p>'
    return f"""<div class="map-table__wrap"><table class="map-table">
<thead><tr><th>연도</th><th>논문</th><th>{esc(third)}</th></tr></thead>
<tbody>{paper_rows(items, note_of)}</tbody>
</table></div>"""


def section(heading: str, inner: str, count: str = "") -> str:
    tail = f'<span class="section__more">{esc(count)}</span>' if count else ""
    return f"""<section class="section">
  <div class="section__head"><h2>{esc(heading)}</h2>{tail}</div>
  {inner}
</section>"""


def by_year(items: list[dict]) -> list[dict]:
    def key(item):
        year = item.get("year", "")
        return (-int(year) if str(year).isdigit() else 0, title_of(item))
    return sorted(items, key=key)


# ──────────────────────────────────────────────────────────────
# 페이지
# ──────────────────────────────────────────────────────────────

MAP_CSS = """<style>
.map-figure{margin:1.4rem 0;padding:0;}
.map-figure svg{width:100%;height:auto;display:block;}
.map-lead{font-size:1.05rem;line-height:1.75;}
.map-table__wrap{overflow-x:auto;}
.map-table{width:100%;border-collapse:collapse;font-size:.94rem;margin:.6rem 0 0;}
.map-table th,.map-table td{text-align:left;vertical-align:top;padding:.55rem .6rem;
  border-bottom:1px solid var(--line-soft);}
.map-table th{font-size:.82rem;color:var(--muted);font-weight:600;
  border-bottom:1px solid var(--line);white-space:nowrap;}
.map-table__year{color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums;}
.map-table__note{color:var(--muted);font-size:.88rem;}
.map-note{color:var(--muted);font-size:.9rem;}
</style>"""


def build_map(cfg: dict, papers: dict) -> None:
    items = papers.get("items", [])
    korean = [i for i in items if i.get("group") == "국문"]
    english = [i for i in items if i.get("group") == "영문"]

    buckets: dict[str, list[dict]] = {}
    for name, queries in AREAS:
        buckets[name] = [i for i in korean if i.get("query") in queries]

    rows = [(name, len(buckets[name]),
             len([i for i in buckets[name] if is_literary(i)]))
            for name, _ in AREAS]

    poetry = buckets["현대시·시교육"]
    poetry_lit = [i for i in poetry if is_literary(i)]
    poetry_inter = [i for i in poetry_lit if is_intercultural(i)]
    multi = buckets["다문화·상호문화교육"]
    multi_lit = [i for i in multi if is_literary(i)]
    letters_lit = [i for i in buckets["문학교육·국어과 교육과정"] if is_literary(i)]
    unity = buckets["통일교육·북한이탈"]
    unity_lit = [i for i in unity if is_literary(i)]
    english_lit = [i for i in english if is_literary(i)]

    lookup = index_items(items)
    picked: dict[str, list[tuple[dict, str]]] = {}
    for group, key, note in load_picks():
        found = lookup.get(doi_key(key))
        if found:
            picked.setdefault(group, []).append((found, note))

    def picked_table(group: str) -> str:
        chosen = picked.get(group, [])
        if not chosen:
            return '<p class="empty">아직 고른 논문이 없습니다. <code>data/map_picks.txt</code> 에 적으세요.</p>'
        notes = {id(item): note for item, note in chosen}
        return paper_table(
            [item for item, _ in chosen], "왜 보는가",
            note_of=lambda item: esc(notes.get(id(item), "")),
        )

    stamp = papers.get("updated", "")
    parts = [MAP_CSS]

    parts.append(f"""<div class="page-head">
  <p class="page-head__eyebrow">선행연구 지도</p>
  <h1>현대시교육 선행연구 지도</h1>
  <p>모아둔 논문 {len(items)}편을 제목 수준에서 갈라 지도로 옮긴 것입니다. 수집될 때마다 다시 계산됩니다.</p>
</div>""")

    parts.append(f"""<p class="map-lead">한 문장으로 줄이면, 연구의 중심인 현대시·시교육이 국문
{len(poetry)}편으로 가장 얇고 인접한 다문화·상호문화교육이 {len(multi)}편으로 가장 두껍습니다.
그런데 그 두꺼운 쪽은 문학 텍스트를 거의 쓰지 않아서, 두 영역을 잇는 연구가 드뭅니다.</p>""")

    parts.append(bar_chart(rows))

    parts.append(section(
        "현대시·시교육",
        f"""<p>검색어 네 개에 {len(poetry)}편이 걸렸고 그중 {len(poetry_lit)}편이 실제로
문학 텍스트를 다룹니다. 나머지는 검색어가 넓어 따라 들어온 것입니다.
상호문화 쪽을 향한 것은 {len(poetry_inter)}편뿐입니다.</p>"""
        + paper_table(by_year(poetry_lit), "학술지"),
        f"{len(poetry_lit)}편",
    ))

    parts.append(section(
        "다문화·상호문화교육",
        f"""<p>{len(multi)}편으로 가장 두꺼운 영역인데 문학 텍스트를 다룬 것은
{len(multi_lit)}편뿐입니다. 나머지는 실태와 정책, 교사 역량, 인식 조사가 중심이어서
무엇을 어떤 텍스트로 가르칠지는 거의 비어 있습니다. 쓰인 장르도 설화·전래동화·그림책·영화에
쏠려 있고 현대시는 들어가 있지 않습니다.</p>"""
        + paper_table(by_year(multi_lit), "학술지"),
        f"{len(multi_lit)}편",
    ))

    parts.append(section(
        "통일교육·북한이탈",
        f"""<p>{len(unity)}편이 쌓였지만 문학 텍스트를 쓴 것은 {len(unity_lit)}편입니다.
이 영역의 주인은 도덕·윤리과이고, 나머지는 정책 평가와 법제 검토, 인식 조사입니다.
문학교육은 아직 진입하지 않았습니다.</p>"""
        + picked_table("통일교육에서 길을 여는 논문"),
        f"{len(unity)}편",
    ))

    parts.append(section(
        "문학교육이 이미 가진 언어",
        f"""<p>문학교육·국어과 교육과정 {len(buckets["문학교육·국어과 교육과정"])}편 가운데
{len(letters_lit)}편이 문학 텍스트를 다룹니다. 여기서 가장 쓸모 있는 발견은,
상호문화교육이라는 이름을 쓰지 않으면서 같은 문제를 다룬 연구가 적지 않다는 점입니다.
타자 이해, 공감, 환대, 돌봄, 갈등, 위치성을 정면으로 다루는데 상호문화 검색어로는 걸리지 않습니다.
아래는 손으로 고른 목록이라 자동으로 늘지 않습니다.</p>"""
        + picked_table("문학교육이 이미 가진 언어"),
    ))

    parts.append(section(
        "영문 연구",
        f"""<p>{len(english)}편 가운데 {len(english_lit)}편이 문학을 다룹니다.
수집 조건이 90일·관련도순이라 최근 것만 들어오고 품질은 고릅니다. 등록문이나 단행본 항목도
섞여 있으니 인용 전에 원문을 확인하세요. 그래도 시교육을 불평등·탈식민·공감의 문제와
정면으로 잇는 접근이 여기 모여 있습니다. 국내에 선행연구가 없다는 것은 주제가 성립하지
않는다는 뜻이 아니라 아직 한국어 문학교육의 문제로 옮겨지지 않았다는 뜻으로 읽을 수 있습니다.</p>"""
        + picked_table("국내에 없는 영문 접근"),
        f"{len(english)}편",
    ))

    parts.append(section(
        "비어 있는 자리",
        quadrant(len(multi_lit), len(letters_lit),
                 len(poetry_inter), len(poetry_lit) - len(poetry_inter))
        + """<p>상호문화교육은 문학을 쓸 때 줄거리가 있는 서사 장르로 가고,
현대시교육은 기술로 갑니다. 두 흐름이 교차하는 칸이 가장 얇습니다.
여기서 연구 질문 세 가지가 바로 나옵니다.</p>
<ol>
<li>상호문화교육은 왜 시를 고르지 않았는가. 설화와 영화는 줄거리가 있어 문화 비교가 쉬운데
시는 그렇지 않습니다. 시의 결함일까요, 아직 방법이 없는 것일까요.</li>
<li>문학교육이 이미 가진 언어를 쓸 수 있는가. 공감, 돌봄, 타자 이해, 위치성은 이미 쌓인
개념입니다. 이것을 상호문화교육과 이으면 새 이론을 만들지 않고도 다리가 놓입니다.</li>
<li>누구의 교실인가. 다문화 연구는 한국어교육 맥락에, 통일 연구는 도덕과에 있습니다.
일반 국어 교실에서 한국어가 모국어인 학생과 이주배경 학생이 같은 시를 읽는 상황은
어느 묶음에도 없습니다.</li>
</ol>"""))

    parts.append(section("이 지도를 믿기 전에", f"""
<p class="map-note">제목만 보고 가른 지도입니다. 아카이브에 초록이 없어서 제목·학술지·연도로만
분류했습니다. 어떤 논문이 무엇을 주장하는지는 여기에 없으니, 인용하시려면 원문을 읽으셔야 합니다.
이 페이지는 어떤 원문을 먼저 읽을지 고르는 데 쓰는 것입니다.</p>
<p class="map-note">장르어로 거르는 방식이라 가장자리에서 틀립니다. 예를 들어 바르트의 신화론을
다룬 이론 논문이 '신화' 때문에 문학으로 잡힐 수 있습니다. 그래서 센 편수만 적지 않고
걸린 논문을 전부 표로 펼쳐두었으니 직접 보고 판단하세요.</p>
<p class="map-note">한국어 제목 가운데 일부는 기계번역입니다. 그대로 참고문헌에 옮기지 마세요.
연도가 2027년 이후로 들어온 레코드도 몇 건 있는데 Crossref 쪽 오류입니다.</p>
<p class="map-note">영역별 편수를 연구의 세력으로 읽지 마세요. 양은 검색어 개수와 수집 조건에
따라 정해집니다. 다만 다문화 {len(multi)}편 가운데 문학이 {len(multi_lit)}편이라는 비율은
색인 방식과 무관한 사실이고, 이 지도에서 가장 튼튼한 수치입니다.</p>
<p class="map-note">기준일 {esc(stamp)} · 국문 {len(korean)}편, 영문 {len(english)}편 ·
손으로 고른 목록은 <code>data/map_picks.txt</code> 에서 고칩니다.</p>"""))

    write(OUT / "map" / "index.html", page(
        cfg, depth=1, active="map", title="선행연구 지도",
        body="\n".join(parts),
        description="모아둔 논문을 영역별로 갈라 현대시교육과 상호문화교육이 만나는 지점을 찾는 지도입니다.",
    ))


def main() -> int:
    if not OUT.exists():
        print("_site/ 가 없습니다. 먼저 scripts/build.py 를 실행하세요.")
        return 1
    cfg = load_config()
    papers = read_json(ROOT / "data" / "studies.json", {"items": []})
    build_map(cfg, papers)
    total = len(papers.get("items", []))
    print(f"선행연구 지도 — 논문 {total}편을 읽어 _site/map/index.html 을 만들었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
