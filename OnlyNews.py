from __future__ import annotations

import argparse
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

import feedparser


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = Path(os.getenv("ONLYNEWS_OUTPUT_DIR", BASE_DIR / "news"))
DEFAULT_LIMIT_PER_FEED = int(os.getenv("ONLYNEWS_LIMIT_PER_FEED", "10"))
STATE_FILE_NAME = ".onlynews-state.json"

# Edit these feeds directly. Group names are used for folders and tags.
RSS_FEEDS: dict[str, list[str]] = {
    "General": [
        # "https://example.com/rss.xml",
    ],
}

SITE_LINKS = {
    "Dashboard Hub": "./index.html",
    "Documents": "./documents/",
    "Earthquakes": "./earthquakes/",
}

ARTICLE_TEMPLATE = """---
Title: "{title}"
aliases:
  - "{title}"
Date: "{isoDate}"
Type: Article

Source: "[[{source}]]"
feedTitle: "{feedTitle}"
Authors: "[[{author}]]"
Link: "{link}"
tags:
  - Sources📥/InternetClippings🌐
  - {tags}
Status: 🟥
Uplink: "[[{uplink}]]"
---

# {title}

## Summary

> [!warning] Summary
> `INPUT[textArea:Summary]`

## Key points
- 
- 
- 

## Notes
-

## Article content
{content}

## Related
- [[Dashboard Hub]]
- [[Documents]]
- [[Earthquakes]]
- [[{source}]]

[Open article]({link})
"""

SOURCE_TEMPLATE = """---
Title: "{title}"
Type: Source
Link: "{link}"
Uplink: "[[{uplink}]]"
---

# {title}

RSS feed: [Open source]({link})

## Related
- [[Dashboard Hub]]
- [[Documents]]
- [[Earthquakes]]
{site_links}

## Recent articles
{recent_articles}
"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("onlynews")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or "item"


def safe_note_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r'[\\/:*?"<>|]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "Untitled"


def yaml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ")


def clean_text(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", value)
    value = re.sub(r"(?i)</\s*p\s*>", "\n\n", value)
    value = re.sub(r"(?i)<\s*p[^>]*>", "", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = unescape(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def get_entry_datetime(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass

    for key in ("published", "updated"):
        raw_value = entry.get(key)
        if raw_value:
            try:
                return parsedate_to_datetime(raw_value).astimezone(timezone.utc)
            except Exception:
                pass

    return datetime.now(timezone.utc)


def isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def pick_author(entry, feed_title: str) -> str:
    authors = entry.get("authors") or []
    if authors:
        first_author = authors[0]
        if isinstance(first_author, dict):
            return first_author.get("name") or first_author.get("email") or feed_title
        return str(first_author)

    return entry.get("author") or feed_title


def pick_entry_content(entry) -> str:
    content_items = entry.get("content") or []
    content_bits: list[str] = []

    for item in content_items:
        if isinstance(item, dict):
            content_bits.append(clean_text(item.get("value", "")))
        else:
            content_bits.append(clean_text(str(item)))

    if content_bits:
        return "\n\n".join(bit for bit in content_bits if bit)

    summary = entry.get("summary") or entry.get("description") or ""
    cleaned_summary = clean_text(summary)
    return cleaned_summary or "_No article content was provided by the feed._"


def build_tags(group_name: str, feed_title: str, entry) -> str:
    tags = ["rss"]

    group_slug = slugify(group_name)
    if group_slug:
        tags.append(f"rss/{group_slug}")

    feed_slug = slugify(feed_title)
    if feed_slug:
        tags.append(f"rss/{feed_slug}")

    for tag in entry.get("tags") or []:
        term = ""
        if isinstance(tag, dict):
            term = tag.get("term") or tag.get("label") or ""
        else:
            term = str(tag)

        term = slugify(term)
        if term:
            tags.append(f"rss/{term}")

    unique_tags: list[str] = []
    seen = set()
    for tag in tags:
        if tag not in seen:
            unique_tags.append(tag)
            seen.add(tag)

    return "\n  - ".join(f'"{tag}"' for tag in unique_tags)


def render_article_note(entry, group_name: str, feed_title: str, source_note: str) -> str:
    title = yaml_escape(entry.get("title", "").strip())
    link = yaml_escape(entry.get("link", "").strip())
    author = yaml_escape(pick_author(entry, feed_title))
    iso_date = isoformat(get_entry_datetime(entry))
    content = pick_entry_content(entry)
    tags = build_tags(group_name, feed_title, entry)

    return ARTICLE_TEMPLATE.format(
        title=title,
        isoDate=iso_date,
        source=yaml_escape(source_note),
        feedTitle=yaml_escape(feed_title),
        author=author,
        link=link,
        tags=tags,
        uplink=yaml_escape("Dashboard Hub"),
        content=content,
    )


def render_source_note(feed_title: str, feed_url: str, recent_articles: list[str]) -> str:
    article_links = "\n".join(f"- [[{safe_note_name(name)}]]" for name in recent_articles) if recent_articles else "- No recent articles yet."
    site_links = "\n".join(f"- [[{note_name}]]" for note_name in SITE_LINKS.keys())

    return SOURCE_TEMPLATE.format(
        title=yaml_escape(feed_title),
        link=yaml_escape(feed_url),
        uplink=yaml_escape("Dashboard Hub"),
        site_links=site_links,
        recent_articles=article_links,
    )


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {"seen": []}

    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("State file is unreadable, starting fresh: %s", state_file)
        return {"seen": []}


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def entry_fingerprint(entry) -> str:
    for key in ("id", "guid", "link"):
        value = entry.get(key)
        if value:
            return str(value)

    title = entry.get("title", "").strip()
    published = entry.get("published", "") or entry.get("updated", "")
    return f"{title}|{published}"


def write_text_file(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        logger.info("[dry-run] would write %s", path)
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def process_feed(group_name: str, feed_url: str, output_dir: Path, limit_per_feed: int, seen: set[str], dry_run: bool) -> tuple[int, list[str]]:
    logger.info("Fetching [%s] %s", group_name, feed_url)
    parsed_feed = feedparser.parse(feed_url)
    if getattr(parsed_feed, "bozo", False):
        logger.warning("Feed parse warning for %s: %s", feed_url, getattr(parsed_feed, "bozo_exception", "unknown issue"))

    feed_title = parsed_feed.feed.get("title", feed_url).strip() or feed_url
    source_note = safe_note_name(feed_title)
    source_dir = output_dir / "sources"
    article_dir = output_dir / "articles" / slugify(group_name)
    created_articles: list[str] = []
    inserted = 0

    for entry in parsed_feed.entries[:limit_per_feed]:
        fingerprint = entry_fingerprint(entry)
        if fingerprint in seen:
            continue

        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue

        note_name = safe_note_name(f"{isoformat(get_entry_datetime(entry))[:10]} {title}")
        note_path = article_dir / f"{note_name}.md"
        note_content = render_article_note(entry, group_name, feed_title, source_note)
        write_text_file(note_path, note_content, dry_run=dry_run)
        seen.add(fingerprint)
        created_articles.append(note_name)
        inserted += 1
        logger.info("  Saved article: %s", note_path)

    source_path = source_dir / f"{source_note}.md"
    source_note_content = render_source_note(feed_title, feed_url, created_articles[:5])
    write_text_file(source_path, source_note_content, dry_run=dry_run)
    logger.info("  Saved source note: %s", source_path)

    return inserted, created_articles


def run(output_dir: Path, limit_per_feed: int, dry_run: bool = False) -> None:
    state_file = output_dir / STATE_FILE_NAME
    state = load_state(state_file)
    seen = set(state.get("seen", []))

    total_created = 0

    if not any(RSS_FEEDS.values()):
        logger.warning("No RSS feeds configured. Add URLs to RSS_FEEDS at the top of OnlyNews.py.")
        return

    for group_name, feed_urls in RSS_FEEDS.items():
        if not feed_urls:
            continue

        logger.info("=== %s ===", group_name)
        for feed_url in feed_urls:
            created, _ = process_feed(group_name, feed_url, output_dir, limit_per_feed, seen, dry_run)
            total_created += created

    state["seen"] = sorted(seen)
    if dry_run:
        logger.info("[dry-run] skipping state save")
    else:
        save_state(state_file, state)

    logger.info("Done. Created %d new article notes in %s.", total_created, output_dir)
    logger.info("Article notes link back to Dashboard Hub, Documents, and Earthquakes.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect RSS feeds into Obsidian-friendly notes.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where article and source notes are written.",
    )
    parser.add_argument(
        "--limit-per-feed",
        type=int,
        default=DEFAULT_LIMIT_PER_FEED,
        help="Maximum number of entries to inspect from each feed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse feeds and report what would be written without saving files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(Path(args.output), args.limit_per_feed, args.dry_run)


if __name__ == "__main__":
    main()
