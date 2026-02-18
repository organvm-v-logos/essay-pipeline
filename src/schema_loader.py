"""Load and cache the frontmatter schema from editorial-standards."""

from pathlib import Path

import yaml


def load_schema(schema_path: str) -> dict:
    """Load frontmatter schema from a local YAML file.

    Args:
        schema_path: Path to frontmatter-schema.yaml

    Returns:
        Parsed schema dict with 'required_fields' key.

    Raises:
        FileNotFoundError: If schema file doesn't exist.
        ValueError: If schema is missing 'required_fields'.
    """
    path = Path(schema_path)
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")

    with open(path) as f:
        schema = yaml.safe_load(f)

    if not isinstance(schema, dict) or "required_fields" not in schema:
        raise ValueError(f"Schema missing 'required_fields' key: {schema_path}")

    return schema
