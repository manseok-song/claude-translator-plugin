#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_builder.py - 번역된 마크다운을 EPUB으로 변환하는 유틸리티

사용법:
    python3 epub_builder.py <markdown_file> [--title TITLE] [--author AUTHOR] [--lang LANG] [--cover COVER_IMAGE] [--media-dir MEDIA_DIR]

예시:
    python3 epub_builder.py output/BLACK_HAWK_WAR_ko.md --title "블랙호크 전쟁" --author "원저자" --lang ko --cover output/media/image1.jpeg
"""

import argparse
import os
import re
import sys
import json
from pathlib import Path

try:
    from ebooklib import epub
except ImportError:
    print("ebooklib이 설치되어 있지 않습니다. 설치 중...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "ebooklib"])
    from ebooklib import epub


# ──────────────────────────────────────────────
# 마크다운 → HTML 변환
# ──────────────────────────────────────────────

def md_to_html(md_text: str) -> str:
    """마크다운 텍스트를 EPUB 호환 XHTML로 변환 (외부 의존성 없음)"""
    lines = md_text.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # 빈 줄
        if not stripped:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("")
            continue

        # 헤딩 (# ~ ######)
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            level = len(heading_match.group(1))
            text = inline_format(heading_match.group(2))
            html_lines.append(f"<h{level}>{text}</h{level}>")
            continue

        # 리스트 아이템
        list_match = re.match(r'^[-*+]\s+(.+)$', stripped)
        if list_match:
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            text = inline_format(list_match.group(1))
            html_lines.append(f"  <li>{text}</li>")
            continue

        # 이미지
        img_match = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
        if img_match:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            alt = img_match.group(1)
            src = img_match.group(2)
            # 이미지 경로를 EPUB 내부 경로로 변환
            img_filename = os.path.basename(src)
            html_lines.append(f'<p><img src="images/{img_filename}" alt="{alt}"/></p>')
            continue

        # 일반 문단
        if in_list:
            html_lines.append("</ul>")
            in_list = False
        text = inline_format(stripped)
        html_lines.append(f"<p>{text}</p>")

    if in_list:
        html_lines.append("</ul>")

    return "\n".join(html_lines)


def inline_format(text: str) -> str:
    """인라인 마크다운 서식 변환 (볼드, 이탤릭, 인라인 이미지)"""
    # 인라인 이미지
    text = re.sub(
        r'!\[([^\]]*)\]\(([^)]+)\)',
        lambda m: f'<img src="images/{os.path.basename(m.group(2))}" alt="{m.group(1)}"/>',
        text
    )
    # 볼드+이탤릭
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    # 볼드
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # 이탤릭
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    # XML 특수문자 이스케이프 (이미 태그가 있으므로 & 만)
    text = text.replace("&", "&amp;").replace("&amp;amp;", "&amp;")
    return text


# ──────────────────────────────────────────────
# 챕터 감지 및 분할
# ──────────────────────────────────────────────

# 챕터/섹션 감지 패턴 (한국어, 영어, 일본어 지원)
CHAPTER_PATTERNS = [
    r'^#\s+',                           # Markdown H1
    r'^##\s+',                          # Markdown H2
    r'^\s*제?\s*\d+\s*부',              # 제1부, 1부
    r'^\s*제?\s*\d+\s*장',              # 제1장, 1장
    r'^\s*제?\s*\d+\s*편',              # 제1편, 1편
    r'^\s*Chapter\s+\d+',              # Chapter 1
    r'^\s*Part\s+\d+',                 # Part 1
    r'^\s*PART\s+[IVX\d]+',           # PART I, PART 1
    r'^\s*第\s*\d+\s*[章部編]',         # 일본어/중국어: 第1章
    r'^\s*프롤로그',                     # 프롤로그
    r'^\s*에필로그',                     # 에필로그
    r'^\s*서문',                         # 서문
    r'^\s*Prologue',                    # Prologue
    r'^\s*Epilogue',                    # Epilogue
    r'^\s*Preface',                     # Preface
    r'^\s*Introduction',               # Introduction
]


def detect_chapters(md_text: str) -> list:
    """
    마크다운 텍스트에서 챕터 경계를 감지하여 분할

    Returns:
        list of dict: [{"title": str, "content": str, "level": int}, ...]
    """
    lines = md_text.split("\n")
    chapters = []
    current_title = None
    current_lines = []
    current_level = 1

    for line in lines:
        stripped = line.strip()

        # 마크다운 헤딩 감지
        h1_match = re.match(r'^#\s+(.+)$', stripped)
        h2_match = re.match(r'^##\s+(.+)$', stripped)

        is_chapter = False
        title = None
        level = 1

        if h1_match:
            is_chapter = True
            title = h1_match.group(1).strip()
            level = 1
        elif h2_match:
            is_chapter = True
            title = h2_match.group(1).strip()
            level = 2
        else:
            # 패턴 기반 감지 (헤딩이 아닌 경우)
            for pattern in CHAPTER_PATTERNS[2:]:  # H1/H2 패턴 제외
                if re.match(pattern, stripped, re.IGNORECASE):
                    is_chapter = True
                    title = stripped
                    level = 1
                    break

        if is_chapter and title:
            # 이전 챕터 저장
            if current_title is not None or current_lines:
                chapters.append({
                    "title": current_title or "서두",
                    "content": "\n".join(current_lines),
                    "level": current_level
                })
            current_title = title
            current_lines = []
            current_level = level
        else:
            current_lines.append(line)

    # 마지막 챕터 저장
    if current_title is not None or current_lines:
        chapters.append({
            "title": current_title or "본문",
            "content": "\n".join(current_lines),
            "level": current_level
        })

    # 챕터가 하나도 감지되지 않으면 전체를 하나의 챕터로
    if not chapters:
        chapters.append({
            "title": "본문",
            "content": md_text,
            "level": 1
        })

    return chapters


# ──────────────────────────────────────────────
# 이미지 수집
# ──────────────────────────────────────────────

def collect_images(media_dir: str) -> list:
    """media 디렉토리에서 이미지 파일을 수집"""
    images = []
    if not media_dir or not os.path.isdir(media_dir):
        return images

    supported_ext = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}
    for fname in sorted(os.listdir(media_dir)):
        ext = os.path.splitext(fname)[1].lower()
        if ext in supported_ext:
            fpath = os.path.join(media_dir, fname)
            mime_map = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".gif": "image/gif",
                ".svg": "image/svg+xml", ".webp": "image/webp"
            }
            images.append({
                "path": fpath,
                "filename": fname,
                "mime_type": mime_map.get(ext, "image/png")
            })
    return images


# ──────────────────────────────────────────────
# CSS 스타일
# ──────────────────────────────────────────────

EPUB_CSS = """
body {
    font-family: serif;
    line-height: 1.8;
    margin: 1em;
    text-align: justify;
}

h1 {
    font-size: 1.6em;
    text-align: center;
    margin-top: 3em;
    margin-bottom: 1.5em;
    page-break-before: always;
}

h2 {
    font-size: 1.3em;
    margin-top: 2em;
    margin-bottom: 1em;
    page-break-before: always;
}

h3 {
    font-size: 1.15em;
    margin-top: 1.5em;
    margin-bottom: 0.8em;
}

p {
    text-indent: 1em;
    margin: 0.3em 0;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1em auto;
}

ul, ol {
    margin: 0.5em 0;
    padding-left: 2em;
}

li {
    margin: 0.2em 0;
}

.cover-page {
    text-align: center;
    padding: 0;
    margin: 0;
}

.cover-page img {
    max-width: 100%;
    max-height: 100%;
}
"""


# ──────────────────────────────────────────────
# EPUB 빌드
# ──────────────────────────────────────────────

def build_epub(
    md_file: str,
    output_path: str = None,
    title: str = None,
    author: str = None,
    language: str = "ko",
    cover_image: str = None,
    media_dir: str = None,
    metadata: dict = None,
) -> str:
    """
    마크다운 파일을 EPUB으로 변환

    Args:
        md_file: 입력 마크다운 파일 경로
        output_path: 출력 EPUB 파일 경로 (None이면 자동 생성)
        title: 책 제목
        author: 저자
        language: 언어 코드 (ko, en, ja 등)
        cover_image: 표지 이미지 경로
        media_dir: 이미지가 있는 디렉토리
        metadata: 추가 메타데이터 dict

    Returns:
        str: 생성된 EPUB 파일 경로
    """
    metadata = metadata or {}

    # 마크다운 읽기
    with open(md_file, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 출력 경로 결정
    if not output_path:
        output_path = os.path.splitext(md_file)[0] + ".epub"

    # 제목/저자 결정
    if not title:
        title = metadata.get("title", Path(md_file).stem)
    if not author:
        author = metadata.get("author", "Unknown")

    # media 디렉토리 자동 감지
    if not media_dir:
        md_dir = os.path.dirname(os.path.abspath(md_file))
        candidate = os.path.join(md_dir, "media")
        if os.path.isdir(candidate):
            media_dir = candidate

    # ──── EPUB 생성 ────
    book = epub.EpubBook()
    book.set_identifier(metadata.get("identifier", f"translator-agent-{Path(md_file).stem}"))
    book.set_title(title)
    book.set_language(language)
    if author and author != "Unknown":
        book.add_author(author)

    # CSS 추가
    css_item = epub.EpubItem(
        uid="style",
        file_name="css/style.css",
        media_type="text/css",
        content=EPUB_CSS.encode("utf-8")
    )
    book.add_item(css_item)

    # 이미지 수집 및 추가
    images = collect_images(media_dir)
    image_items = {}
    for img_info in images:
        with open(img_info["path"], "rb") as f:
            img_data = f.read()
        img_item = epub.EpubItem(
            uid=f"img_{img_info['filename'].replace('.', '_')}",
            file_name=f"images/{img_info['filename']}",
            media_type=img_info["mime_type"],
            content=img_data
        )
        book.add_item(img_item)
        image_items[img_info["filename"]] = img_item

    # 표지 이미지 설정
    if cover_image and os.path.exists(cover_image):
        with open(cover_image, "rb") as f:
            cover_data = f.read()
        cover_filename = os.path.basename(cover_image)
        book.set_cover(cover_filename, cover_data)
    elif images:
        # 첫 번째 이미지를 표지로 사용
        with open(images[0]["path"], "rb") as f:
            cover_data = f.read()
        book.set_cover(images[0]["filename"], cover_data)

    # 챕터 감지 및 분할
    chapters = detect_chapters(md_text)
    epub_chapters = []
    toc_items = []

    for i, ch in enumerate(chapters):
        chapter_html = md_to_html(ch["content"])

        xhtml_content = f'''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{language}">
<head>
    <title>{ch["title"]}</title>
    <link href="css/style.css" rel="stylesheet" type="text/css"/>
</head>
<body>
    <h{ch["level"]}>{ch["title"]}</h{ch["level"]}>
    {chapter_html}
</body>
</html>'''

        epub_ch = epub.EpubHtml(
            title=ch["title"],
            file_name=f"chapter_{i+1:03d}.xhtml",
            lang=language,
            content=xhtml_content.encode("utf-8")
        )
        epub_ch.add_item(css_item)
        book.add_item(epub_ch)
        epub_chapters.append(epub_ch)

        # TOC 항목
        toc_items.append(epub.Link(
            f"chapter_{i+1:03d}.xhtml",
            ch["title"],
            f"chapter_{i+1:03d}"
        ))

    # TOC 설정
    book.toc = toc_items

    # Navigation 파일
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Spine 구성
    book.spine = ["nav"] + epub_chapters

    # EPUB 저장
    epub.write_epub(output_path, book, {})

    return output_path


# ──────────────────────────────────────────────
# glossary.json에서 메타데이터 추출
# ──────────────────────────────────────────────

def extract_metadata_from_glossary(glossary_path: str) -> dict:
    """glossary.json에서 메타데이터 힌트를 추출"""
    metadata = {}
    if not glossary_path or not os.path.exists(glossary_path):
        return metadata

    try:
        with open(glossary_path, "r", encoding="utf-8") as f:
            glossary = json.load(f)
        meta = glossary.get("metadata", {})
        if "source_language" in meta:
            metadata["source_language"] = meta["source_language"]
        if "target_language" in meta:
            metadata["language"] = meta["target_language"]
    except (json.JSONDecodeError, KeyError):
        pass

    return metadata


# ──────────────────────────────────────────────
# CLI 엔트리포인트
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="번역된 마크다운을 EPUB으로 변환",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python3 epub_builder.py output/book_ko.md
  python3 epub_builder.py output/book_ko.md --title "책 제목" --author "저자명"
  python3 epub_builder.py output/book_ko.md --cover output/media/image1.jpeg --media-dir output/media
  python3 epub_builder.py output/book_ko.md --glossary output/glossary.json
        """
    )
    parser.add_argument("markdown_file", help="입력 마크다운 파일 경로")
    parser.add_argument("-o", "--output", help="출력 EPUB 파일 경로")
    parser.add_argument("--title", help="책 제목")
    parser.add_argument("--author", help="저자")
    parser.add_argument("--lang", default="ko", help="언어 코드 (기본: ko)")
    parser.add_argument("--cover", help="표지 이미지 경로")
    parser.add_argument("--media-dir", help="이미지 디렉토리 경로")
    parser.add_argument("--glossary", help="glossary.json 경로 (메타데이터 추출용)")

    args = parser.parse_args()

    if not os.path.exists(args.markdown_file):
        print(f"오류: 파일을 찾을 수 없습니다: {args.markdown_file}")
        sys.exit(1)

    # glossary에서 메타데이터 추출
    metadata = {}
    if args.glossary:
        metadata = extract_metadata_from_glossary(args.glossary)

    # EPUB 빌드
    output = build_epub(
        md_file=args.markdown_file,
        output_path=args.output,
        title=args.title,
        author=args.author,
        language=args.lang,
        cover_image=args.cover,
        media_dir=args.media_dir,
        metadata=metadata,
    )

    file_size = os.path.getsize(output)
    print(f"EPUB 생성 완료: {output} ({file_size:,} bytes)")


if __name__ == "__main__":
    main()
