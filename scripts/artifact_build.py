#!/usr/bin/env python3
"""
아티팩트용 사본 만들기 — _site/ 를 _artifact/ 로 옮기며 두 가지를 고칩니다.

  1) 디렉터리 링크(trends/)를 파일 링크(trends/index.html)로 바꿉니다.
     아티팩트 호스팅은 디렉터리 주소를 index.html 로 풀어주지 않습니다.
  2) 외부 CDN 글꼴을 구글 폰트로 바꿉니다.
     아티팩트 보안 정책이 CDN 스타일시트를 막습니다.

  python3 scripts/build.py && python3 scripts/artifact_build.py
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "_site"
OUT = ROOT / "_artifact"

CDN_FONT = (
    '<link rel="stylesheet" '
    'href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9'
    '/dist/web/static/pretendard.min.css">'
)
GOOGLE_FONT = (
    '<link rel="stylesheet" '
    'href="https://fonts.googleapis.com/css2?'
    'family=Noto+Sans+KR:wght@400;500;600;700&display=swap">'
)


BASE_URL = ""
try:
    import json as _json
    BASE_URL = _json.loads((ROOT / "config.json").read_text(encoding="utf-8")) \
        .get("site", {}).get("base_url", "").rstrip("/")
except Exception:
    pass


def main() -> int:
    if not SITE.exists():
        print("_site/ 가 없습니다. 먼저 scripts/build.py 를 실행하세요.")
        return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE, OUT)

    # 자료실 파일은 아티팩트에 싣지 않고 사이트 주소로 연결합니다.
    # 매번 올리면 아티팩트가 무거워지고, 같은 파일이 두 곳에 생깁니다.
    files_dir = OUT / "files"
    if files_dir.exists():
        shutil.rmtree(files_dir)

    for path in OUT.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        # 앞의 ./ 또는 ../ 반복을 모두 받습니다.
        prefix = r'((?:\./|(?:\.\./)+)?)'
        text = re.sub(rf'href="{prefix}(trends|studies|library)/"',
                      r'href="\1\2/index.html"', text)
        # 날짜 폴더 링크: trends/2026-11-03/ · 2026-11-03/ · ../2026-11-02/ 모두.
        text = re.sub(rf'href="{prefix}((?:trends/)?\d{{4}}-\d{{2}}-\d{{2}})/"',
                      r'href="\1\2/index.html"', text)
        text = re.sub(r'href="\./"', 'href="./index.html"', text)
        text = re.sub(r'href="((?:\.\./)+)"', r'href="\1index.html"', text)
        text = text.replace(CDN_FONT, GOOGLE_FONT)
        if BASE_URL:
            text = re.sub(r'href="(?:\.\./)*files/',
                          f'href="{BASE_URL}/files/', text)
        path.write_text(text, encoding="utf-8")

    css = OUT / "assets" / "style.css"
    if css.exists():
        body = css.read_text(encoding="utf-8")
        css.write_text(
            body.replace('--sans:  Pretendard,', '--sans:  "Noto Sans KR", Pretendard,'),
            encoding="utf-8",
        )

    pages = sorted(p.relative_to(OUT).as_posix() for p in OUT.rglob("*.html"))
    print(f"_artifact/ 준비 완료 — {len(pages)}개 페이지")
    for page in pages:
        print("  ", page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
