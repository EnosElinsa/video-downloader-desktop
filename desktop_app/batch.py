"""Markdown chapter/section batch downloader."""

from __future__ import annotations

import argparse
import logging
import os
import re
from pathlib import Path

from .cli import download_video
from .filenames import sanitize_filename
from .security import install_redaction, sanitize_message

logger = logging.getLogger(__name__)
install_redaction(logger)


def parse_markdown_file(file_path: str | os.PathLike[str]) -> list[dict]:
    """Extract chapters, numbered sections, descriptions, and HTTP(S) links."""
    content = Path(file_path).read_text(encoding="utf-8")
    chapter_pattern = re.compile(r"(序\s*章|第[一二三四五六七八九十]+篇章)\s*([^（\n]+)")
    section_pattern = re.compile(r"^(\d+)[\.、]([^\n]+)")
    url_pattern = re.compile(r"https?://[^\s)\"<]+")
    chapters: list[dict] = []
    current_chapter = None
    current_section = None
    for line in content.splitlines():
        chapter_match = chapter_pattern.search(line)
        if chapter_match:
            current_chapter = {
                "number": chapter_match.group(1),
                "title": chapter_match.group(2).strip(),
                "sections": [],
            }
            chapters.append(current_chapter)
            current_section = None
            continue
        section_match = section_pattern.search(line)
        if section_match and current_chapter is not None:
            current_section = {
                "number": section_match.group(1),
                "title": section_match.group(2).strip(),
                "videos": [],
            }
            current_chapter["sections"].append(current_section)
            continue
        if current_section is None:
            continue
        for url in url_pattern.findall(line):
            current_section["videos"].append(
                {"url": url, "description": line.split(url, 1)[0].strip()}
            )
    return chapters


def create_folder_structure(chapter_data: list[dict], base_dir="videos") -> None:
    """Create the chapter/section folders used by the batch output."""
    root = Path(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    for chapter in chapter_data:
        chapter_dir = root / sanitize_filename(
            f"{chapter['number']}_{chapter['title']}"
        )
        for section in chapter["sections"]:
            (chapter_dir / sanitize_filename(
                f"{section['number']}_{section['title']}"
            )).mkdir(parents=True, exist_ok=True)


def download_videos(chapter_data: list[dict], base_dir="videos") -> None:
    """Download every discovered URL through the shared download interface."""
    root = Path(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    unsupported = root / "unsupported_urls.txt"
    unsupported.write_text("# Unsupported URLs for manual download\n\n", encoding="utf-8")
    for chapter in chapter_data:
        chapter_dir = root / sanitize_filename(
            f"{chapter['number']}_{chapter['title']}"
        )
        for section in chapter["sections"]:
            section_dir = chapter_dir / sanitize_filename(
                f"{section['number']}_{section['title']}"
            )
            section_dir.mkdir(parents=True, exist_ok=True)
            for index, video in enumerate(section["videos"], start=1):
                url = video["url"]
                description = video["description"]
                name = f"{index}_{sanitize_filename((description or 'video')[:30])}"
                result = download_video(
                    url,
                    section_dir,
                    output_template=str(section_dir / f"{name}.%(ext)s"),
                )
                if result:
                    logger.info("Downloaded %s", name)
                    continue
                logger.error("Could not download %s", sanitize_message(url))
                with unsupported.open("a", encoding="utf-8") as handle:
                    handle.write(
                        f"Chapter: {chapter['number']} - {chapter['title']}\n"
                        f"Section: {section['number']} - {section['title']}\n"
                        f"Video {index}: {description}\nURL: {url}\n\n"
                    )
                (section_dir / f"{name}.url").write_text(
                    f"[InternetShortcut]\nURL={url}\n", encoding="utf-8"
                )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract and download videos listed in a structured Markdown file."
    )
    parser.add_argument("--source", default="source.md", help="Markdown source file")
    parser.add_argument("--output", default="videos", help="Output directory")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    source = Path(args.source)
    if not source.is_file():
        parser.error(f"source file does not exist: {source}")
    chapters = parse_markdown_file(source)
    if not chapters:
        logger.error("No chapters were found in %s", source)
        return 1
    create_folder_structure(chapters, args.output)
    download_videos(chapters, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
