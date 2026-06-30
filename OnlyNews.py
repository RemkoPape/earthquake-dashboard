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
def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(BASE_DIR / ".env")
DEFAULT_OUTPUT_DIR = Path(os.getenv("ONLYNEWS_OUTPUT_DIR", BASE_DIR / "news"))
DEFAULT_LIMIT_PER_FEED = int(os.getenv("ONLYNEWS_LIMIT_PER_FEED", "8"))
STATE_FILE_NAME = ".onlynews-state.json"
FEED_JSON_NAME = "feed.json"

FEED_SOURCES = [
    {
        "title": "WILD HOMESTEAD",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCstLIadsuuLmDdIzMZxesfg",
        "category": "Videos/Enjoyment",
        "kind": "Video",
    },
    {
        "title": "DW Documentary",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCW39zufHfsuGgpLviKh297Q",
        "category": "Videos/Learning",
        "kind": "Video",
    },
    {
        "title": "PBS Terra",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCpxYSWgxVt3Pyn1ovXsGQ0g",
        "category": "Videos/Learning",
        "kind": "Video",
    },
    {
        "title": "Max Fisher",
        "url": "https://rss.app/feeds/OHpTHnmmcQbi7lWw.xml",
        "category": "Videos/Learning",
        "kind": "Video",
    },
    {
        "title": "Astrum Earth",
        "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCWBtLCE-BnzZx3DneqDiXWQ",
        "category": "Videos/Learning",
        "kind": "Video",
    },
    {
        "title": "The Climate Question",
        "url": "https://podcasts.files.bbci.co.uk/w13xtvb6.rss",
        "category": "Podcasts",
        "kind": "Podcast",
    },
    {
        "title": "Science Weekly | The Guardian",
        "url": "https://www.theguardian.com/science/series/science/rss",
        "category": "Podcasts",
        "kind": "Podcast",
    },
    {
        "title": "Carbon Brief",
        "url": "https://www.carbonbrief.org/feed",
        "category": "RSS/Science and Climate",
        "kind": "Article",
    },
    {
        "title": "Eos",
        "url": "https://eos.org/feed",
        "category": "RSS/Science and Climate",
        "kind": "Article",
    },
    {
        "title": "Copernicus",
        "url": "https://climate.copernicus.eu/rss.xml",
        "category": "RSS/Science and Climate",
        "kind": "Article",
    },
    {
        "title": "Science | The Guardian",
        "url": "https://www.theguardian.com/science/rss",
        "category": "RSS/Science and Climate",
        "kind": "Article",
    },
    {
        "title": "BBC News",
        "url": "http://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        "category": "RSS/Science and Climate",
        "kind": "Article",
    },
    {
        "title": "Nisa Blog - All Things Environmental Sustainability",
        "url": "https://feedfry.com/rss/11f1556cf7007b79a9e4704a92375605",
        "category": "RSS/Science and Climate",
        "kind": "Article",
    },
    {
        "title": "FA RSS",
        "url": "https://www.foreignaffairs.com/rss.xml",
        "category": "RSS/Geopolitics",
        "kind": "Article",
    },
    {
        "title": "International Crisis Group",
        "url": "https://www.crisisgroup.org/rss.xml",
        "category": "RSS/Geopolitics",
        "kind": "Article",
    },
]

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
  - Sources\U0001F4E5/InternetClippings\U0001F310
  - {tags}
Status: \U0001F7E5
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
- [[RSS Notes]]
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
- [[RSS Notes]]

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


def shorten_text(value: str, max_length: int = 220) -> str:
    value = clean_text(value)
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


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


def pick_author(entry, fallback: str) -> str:
    authors = entry.get("authors") or []
    if authors:
        first_author = authors[0]
        if isinstance(first_author, dict):
            return first_author.get("name") or first_author.get("email") or fallback
        return str(first_author)
    return entry.get("author") or fallback


def pick_entry_content(entry) -> str:
    content_items = entry.get("content") or []
    parts: list[str] = []

    for item in content_items:
        if isinstance(item, dict):
            parts.append(clean_text(item.get("value", "")))
        else:
            parts.append(clean_text(str(item)))

    if parts:
        joined = "\n\n".join(part for part in parts if part)
        if joined:
            return joined

    summary = entry.get("summary") or entry.get("description") or ""
    cleaned = clean_text(summary)
    return cleaned or "_No article content was provided by the feed._"


def build_tags(category: str, feed_title: str, entry) -> str:
    tags = ["rss", f"rss/{slugify(category)}", f"rss/{slugify(feed_title)}"]

    for tag in entry.get("tags") or []:
        term = tag.get("term") if isinstance(tag, dict) else str(tag)
        term_slug = slugify(term or "")
        if term_slug:
            tags.append(f"rss/{term_slug}")

    unique_tags: list[str] = []
    seen = set()
    for tag in tags:
        if tag and tag not in seen:
            unique_tags.append(tag)
            seen.add(tag)

    return "\n  - ".join(f'"{tag}"' for tag in unique_tags)


def entry_fingerprint(entry) -> str:
    for key in ("id", "guid", "link"):
        value = entry.get(key)
        if value:
            return str(value)
    title = entry.get("title", "").strip()
    published = entry.get("published", "") or entry.get("updated", "")
    return f"{title}|{published}"


def note_name_for_item(title: str, published_at: str) -> str:
    return safe_note_name(f"{published_at[:10]} {title}")


def normalize_item(feed_config: dict[str, str], feed_title: str, entry) -> dict[str, str] | None:
    title = (entry.get("title") or "").strip()
    link = (entry.get("link") or "").strip()
    if not title or not link:
        return None

    published_at = isoformat(get_entry_datetime(entry))
    source_note = safe_note_name(feed_title)
    note_name = note_name_for_item(title, published_at)
    category_slug = slugify(feed_config["category"])

    return {
        "id": entry_fingerprint(entry),
        "title": title,
        "link": link,
        "published_at": published_at,
        "author": pick_author(entry, feed_title),
        "summary": shorten_text(entry.get("summary") or entry.get("description") or pick_entry_content(entry)),
        "content": pick_entry_content(entry),
        "feed_title": feed_title,
        "feed_url": feed_config["url"],
        "feed_label": feed_config["title"],
        "category": feed_config["category"],
        "kind": feed_config["kind"],
        "source_note": source_note,
        "note_name": note_name,
        "article_path": f"articles/{category_slug}/{note_name}.md",
        "source_path": f"sources/{source_note}.md",
    }


def render_article_note(item: dict[str, str], entry) -> str:
    return ARTICLE_TEMPLATE.format(
        title=yaml_escape(item["title"]),
        isoDate=item["published_at"],
        source=yaml_escape(item["source_note"]),
        feedTitle=yaml_escape(item["feed_title"]),
        author=yaml_escape(item["author"]),
        link=yaml_escape(item["link"]),
        tags=build_tags(item["category"], item["feed_title"], entry),
        uplink="RSS Notes",
        content=item["content"],
    )


def render_source_note(feed_title: str, feed_url: str, recent_note_names: list[str]) -> str:
    article_links = "\n".join(f"- [[{safe_note_name(name)}]]" for name in recent_note_names) if recent_note_names else "- No recent articles yet."
    return SOURCE_TEMPLATE.format(
        title=yaml_escape(feed_title),
        link=yaml_escape(feed_url),
        uplink="RSS Notes",
        recent_articles=article_links,
    )


def load_state(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {"seen": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("State file is unreadable, starting fresh: %s", path)
        return {"seen": []}


def save_state(path: Path, state: dict[str, list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text_file(path: Path, content: str, dry_run: bool) -> None:
    if dry_run:
        logger.info("[dry-run] would write %s", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json_file(path: Path, payload: dict, dry_run: bool) -> None:
    if dry_run:
        logger.info("[dry-run] would write %s", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def process_feed(
    feed_config: dict[str, str],
    output_dir: Path,
    limit_per_feed: int,
    seen: set[str],
    dry_run: bool,
) -> tuple[dict[str, str | int], list[dict[str, str]], int]:
    logger.info("Fetching [%s] %s", feed_config["category"], feed_config["url"])
    parsed = feedparser.parse(feed_config["url"])
    if getattr(parsed, "bozo", False):
        logger.warning("Feed parse warning for %s: %s", feed_config["url"], getattr(parsed, "bozo_exception", "unknown issue"))

    feed_title = parsed.feed.get("title", feed_config["title"]).strip() or feed_config["title"]
    source_note = safe_note_name(feed_title)
    feed_items: list[dict[str, str]] = []
    recent_note_names: list[str] = []
    created_count = 0

    for entry in parsed.entries[:limit_per_feed]:
        item = normalize_item(feed_config, feed_title, entry)
        if not item:
            continue

        feed_items.append(item)
        recent_note_names.append(item["note_name"])

        if item["id"] in seen:
            continue

        article_path = output_dir / item["article_path"]
        article_content = render_article_note(item, entry)
        write_text_file(article_path, article_content, dry_run)
        seen.add(item["id"])
        created_count += 1

    source_path = output_dir / "sources" / f"{source_note}.md"
    source_content = render_source_note(feed_title, feed_config["url"], recent_note_names[:5])
    write_text_file(source_path, source_content, dry_run)

    latest_published = feed_items[0]["published_at"] if feed_items else ""
    feed_meta = {
        "title": feed_title,
        "label": feed_config["title"],
        "url": feed_config["url"],
        "category": feed_config["category"],
        "kind": feed_config["kind"],
        "item_count": len(feed_items),
        "new_notes": created_count,
        "latest_published": latest_published,
        "source_path": f"sources/{source_note}.md",
    }
    return feed_meta, feed_items, created_count


def build_feed_payload(feeds_meta: list[dict], items: list[dict[str, str]]) -> dict:
    sorted_items = sorted(items, key=lambda item: item["published_at"], reverse=True)
    sections: list[dict] = []
    categories = sorted({item["category"] for item in sorted_items})

    for category in categories:
        category_items = [item for item in sorted_items if item["category"] == category]
        sections.append(
            {
                "category": category,
                "item_count": len(category_items),
                "items": category_items,
            }
        )

    return {
        "generated_at": isoformat(datetime.now(timezone.utc)),
        "feed_count": len(feeds_meta),
        "item_count": len(sorted_items),
        "feeds": feeds_meta,
        "sections": sections,
        "items": sorted_items,
    }


def run(output_dir: Path, limit_per_feed: int, dry_run: bool = False) -> None:
    state_path = output_dir / STATE_FILE_NAME
    feed_json_path = output_dir / FEED_JSON_NAME
    state = load_state(state_path)
    seen = set(state.get("seen", []))

    all_items: list[dict[str, str]] = []
    feeds_meta: list[dict] = []
    total_new_notes = 0

    for feed_config in FEED_SOURCES:
        meta, items, created_count = process_feed(feed_config, output_dir, limit_per_feed, seen, dry_run)
        feeds_meta.append(meta)
        all_items.extend(items)
        total_new_notes += created_count

    payload = build_feed_payload(feeds_meta, all_items)
    write_json_file(feed_json_path, payload, dry_run)

    state["seen"] = sorted(seen)
    if dry_run:
        logger.info("[dry-run] skipping state save")
    else:
        save_state(state_path, state)

    logger.info("Done. Exported %d feed items across %d feeds.", payload["item_count"], payload["feed_count"])
    logger.info("Created %d new Obsidian article notes in %s.", total_new_notes, output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect selected RSS feeds into Obsidian notes and a local feed JSON file.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where feed JSON, article notes, and source notes are written.",
    )
    parser.add_argument(
        "--limit-per-feed",
        type=int,
        default=DEFAULT_LIMIT_PER_FEED,
        help="Maximum number of items to read from each feed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse feeds and report output without writing files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run(Path(args.output), args.limit_per_feed, args.dry_run)


if __name__ == "__main__":
    main()
