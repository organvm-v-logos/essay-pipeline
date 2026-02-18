"""Frontmatter schema validator for ORGAN-V essays.

Reads YAML frontmatter from Markdown files, validates each field against
the schema defined in editorial-standards/schemas/frontmatter-schema.yaml.

CLI: python -m src.validator --posts-dir _posts/ --schema path/to/frontmatter-schema.yaml
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

from .schema_loader import load_schema


def extract_frontmatter(filepath: Path) -> dict | None:
    """Extract YAML frontmatter from a Markdown file.

    Returns None if no frontmatter delimiters found.
    """
    text = filepath.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        return yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None


def validate_field(field_name: str, value, spec: dict) -> list[str]:
    """Validate a single field value against its schema spec.

    Returns a list of error strings (empty if valid).
    """
    errors = []
    field_type = spec.get("type")

    if field_type == "string":
        if not isinstance(value, str):
            return [f"expected string, got {type(value).__name__}"]
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"must be one of {spec['enum']}, got '{value}'")
        if "min_length" in spec and len(value) < spec["min_length"]:
            errors.append(f"too short ({len(value)} chars, min {spec['min_length']})")
        if "max_length" in spec and len(value) > spec["max_length"]:
            errors.append(f"too long ({len(value)} chars, max {spec['max_length']})")
        if "pattern" in spec and not re.match(spec["pattern"], value):
            errors.append(f"does not match pattern {spec['pattern']}")

    elif field_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return [f"expected integer, got {type(value).__name__}"]
        if "min" in spec and value < spec["min"]:
            errors.append(f"value {value} below minimum {spec['min']}")

    elif field_type == "list":
        if not isinstance(value, list):
            return [f"expected list, got {type(value).__name__}"]
        if "min_items" in spec and len(value) < spec["min_items"]:
            errors.append(f"too few items ({len(value)}, min {spec['min_items']})")
        if "max_items" in spec and len(value) > spec["max_items"]:
            errors.append(f"too many items ({len(value)}, max {spec['max_items']})")
        item_type = spec.get("item_type")
        item_pattern = spec.get("item_pattern")
        for i, item in enumerate(value):
            if item_type == "string" and not isinstance(item, str):
                errors.append(f"item [{i}] expected string, got {type(item).__name__}")
            elif item_pattern and isinstance(item, str) and not re.match(item_pattern, item):
                errors.append(f"item [{i}] '{item}' does not match pattern {item_pattern}")

    return errors


def validate_essay(filepath: Path, schema: dict) -> list[str]:
    """Validate a single essay's frontmatter against the schema.

    Returns a list of error strings (empty if valid).
    """
    fm = extract_frontmatter(filepath)
    if fm is None:
        return [f"{filepath.name}: no valid frontmatter found"]

    errors = []
    required = schema["required_fields"]

    for field_name, spec in required.items():
        if field_name not in fm:
            errors.append(f"{filepath.name}: missing required field '{field_name}'")
            continue
        field_errors = validate_field(field_name, fm[field_name], spec)
        for err in field_errors:
            errors.append(f"{filepath.name}: field '{field_name}' — {err}")

    return errors


def validate_all(posts_dir: str, schema_path: str) -> list[str]:
    """Validate all .md files in posts_dir against the schema.

    Returns a list of all error strings across all files.
    """
    schema = load_schema(schema_path)
    posts = sorted(Path(posts_dir).glob("*.md"))

    if not posts:
        return [f"No .md files found in {posts_dir}"]

    all_errors = []
    for post in posts:
        all_errors.extend(validate_essay(post, schema))

    return all_errors


def main():
    parser = argparse.ArgumentParser(description="Validate essay frontmatter")
    parser.add_argument("--posts-dir", required=True, help="Path to _posts/ directory")
    parser.add_argument("--schema", required=True, help="Path to frontmatter-schema.yaml")
    args = parser.parse_args()

    errors = validate_all(args.posts_dir, args.schema)

    if errors:
        print(f"FAILED — {len(errors)} error(s):\n")
        for err in errors:
            print(f"  {err}")
        sys.exit(1)
    else:
        posts_count = len(list(Path(args.posts_dir).glob("*.md")))
        print(f"PASSED — {posts_count} essays validated, 0 errors")
        sys.exit(0)


if __name__ == "__main__":
    main()
