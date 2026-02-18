"""Essay indexer for ORGAN-V public-process.

Reads all Markdown essays, extracts frontmatter, computes word counts,
and generates structured JSON data files.

CLI: python -m src.indexer --posts-dir _posts/ --output-dir data/
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml


def extract_essay_data(filepath: Path) -> dict | None:
    """Extract frontmatter and compute body word count from a Markdown file."""
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None

    body = parts[2].strip()
    # Strip markdown formatting for word count
    clean = re.sub(r"[#*_`\[\]()>|]", " ", body)
    clean = re.sub(r"https?://\S+", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    word_count = len(clean.split()) if clean else 0

    return {
        "filename": filepath.name,
        "frontmatter": fm,
        "computed_word_count": word_count,
    }


def build_essays_index(essays: list[dict]) -> dict:
    """Build the essays-index.json structure."""
    categories = Counter()
    tags = Counter()
    total_words = 0

    entries = []
    for e in essays:
        fm = e["frontmatter"]
        cat = fm.get("category", "uncategorized")
        categories[cat] += 1
        for tag in fm.get("tags", []):
            tags[tag] += 1
        wc = e["computed_word_count"]
        total_words += wc
        entries.append({
            "filename": e["filename"],
            "title": fm.get("title", ""),
            "date": fm.get("date", ""),
            "category": cat,
            "tags": fm.get("tags", []),
            "word_count": wc,
            "reading_time": fm.get("reading_time", ""),
            "portfolio_relevance": fm.get("portfolio_relevance", ""),
        })

    return {
        "version": "1.1",
        "updated": date.today().isoformat(),
        "generated_by": "essay-pipeline indexer v0.1.0",
        "total_essays": len(essays),
        "total_words": total_words,
        "categories": dict(sorted(categories.items(), key=lambda x: -x[1])),
        "tag_frequency": dict(sorted(tags.items(), key=lambda x: -x[1])),
        "essays": entries,
    }


def build_cross_references(essays: list[dict]) -> dict:
    """Build cross-references.json keyed by filename."""
    refs = {}
    for e in essays:
        fm = e["frontmatter"]
        refs[e["filename"]] = {
            "title": fm.get("title", ""),
            "related_repos": fm.get("related_repos", []),
            "tags": fm.get("tags", []),
            "category": fm.get("category", ""),
        }
    return {
        "version": "1.1",
        "updated": date.today().isoformat(),
        "total": len(refs),
        "entries": refs,
    }


def build_publication_calendar(essays: list[dict]) -> dict:
    """Build publication-calendar.json with essay count by date."""
    by_date = Counter()
    for e in essays:
        d = e["frontmatter"].get("date", "unknown")
        by_date[d] += 1

    return {
        "version": "1.1",
        "updated": date.today().isoformat(),
        "total_essays": len(essays),
        "dates": dict(sorted(by_date.items())),
    }


def index_all(posts_dir: str, output_dir: str) -> dict:
    """Index all essays and write JSON data files.

    Returns a summary dict with counts.
    """
    posts = sorted(Path(posts_dir).glob("*.md"))
    essays = []
    for p in posts:
        data = extract_essay_data(p)
        if data:
            essays.append(data)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    index = build_essays_index(essays)
    xrefs = build_cross_references(essays)
    calendar = build_publication_calendar(essays)

    (out / "essays-index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n"
    )
    (out / "cross-references.json").write_text(
        json.dumps(xrefs, indent=2, ensure_ascii=False) + "\n"
    )
    (out / "publication-calendar.json").write_text(
        json.dumps(calendar, indent=2, ensure_ascii=False) + "\n"
    )

    return {
        "essays": len(essays),
        "categories": len(index["categories"]),
        "total_words": index["total_words"],
    }


def main():
    parser = argparse.ArgumentParser(description="Index essays and generate data files")
    parser.add_argument("--posts-dir", required=True, help="Path to _posts/ directory")
    parser.add_argument("--output-dir", required=True, help="Path to output data/ directory")
    args = parser.parse_args()

    summary = index_all(args.posts_dir, args.output_dir)
    print(
        f"Indexed {summary['essays']} essays across "
        f"{summary['categories']} categories ({summary['total_words']} words)"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
