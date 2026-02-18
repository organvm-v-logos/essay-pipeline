"""Tests for the frontmatter validator."""

from pathlib import Path

from src.schema_loader import load_schema
from src.validator import extract_frontmatter, validate_essay, validate_field

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_PATH = str(
    Path(__file__).parent.parent.parent
    / "editorial-standards"
    / "schemas"
    / "frontmatter-schema.yaml"
)


def get_schema():
    return load_schema(SCHEMA_PATH)


class TestExtractFrontmatter:
    def test_valid_frontmatter(self):
        fm = extract_frontmatter(FIXTURES / "valid-essay.md")
        assert fm is not None
        assert fm["title"] == "A Perfectly Valid Test Essay for the Pipeline"

    def test_no_frontmatter(self, tmp_path):
        p = tmp_path / "no-fm.md"
        p.write_text("# Just a heading\n\nNo frontmatter here.")
        assert extract_frontmatter(p) is None


class TestValidateField:
    def test_string_enum_valid(self):
        spec = {"type": "string", "enum": ["essay"]}
        assert validate_field("layout", "essay", spec) == []

    def test_string_enum_invalid(self):
        spec = {"type": "string", "enum": ["essay"]}
        errors = validate_field("layout", "post", spec)
        assert len(errors) == 1
        assert "must be one of" in errors[0]

    def test_string_pattern_valid(self):
        spec = {"type": "string", "pattern": "^@"}
        assert validate_field("author", "@4444J99", spec) == []

    def test_string_pattern_invalid(self):
        spec = {"type": "string", "pattern": "^@"}
        errors = validate_field("author", "no-prefix", spec)
        assert len(errors) == 1
        assert "pattern" in errors[0]

    def test_string_min_length(self):
        spec = {"type": "string", "min_length": 50}
        errors = validate_field("excerpt", "Too short.", spec)
        assert any("too short" in e for e in errors)

    def test_integer_valid(self):
        spec = {"type": "integer", "min": 500}
        assert validate_field("word_count", 1000, spec) == []

    def test_integer_below_min(self):
        spec = {"type": "integer", "min": 500}
        errors = validate_field("word_count", 100, spec)
        assert any("below minimum" in e for e in errors)

    def test_integer_wrong_type(self):
        spec = {"type": "integer", "min": 500}
        errors = validate_field("word_count", "not a number", spec)
        assert any("expected integer" in e for e in errors)

    def test_list_valid(self):
        spec = {"type": "list", "min_items": 2, "max_items": 8, "item_type": "string"}
        assert validate_field("tags", ["a", "b"], spec) == []

    def test_list_too_few(self):
        spec = {"type": "list", "min_items": 2, "max_items": 8, "item_type": "string"}
        errors = validate_field("tags", ["only-one"], spec)
        assert any("too few" in e for e in errors)

    def test_list_item_pattern(self):
        spec = {
            "type": "list",
            "item_type": "string",
            "item_pattern": "^(organvm-|meta-organvm)",
        }
        errors = validate_field("related_repos", ["bad-repo"], spec)
        assert any("pattern" in e for e in errors)


class TestValidateEssay:
    def test_valid_essay_passes(self):
        schema = get_schema()
        errors = validate_essay(FIXTURES / "valid-essay.md", schema)
        assert errors == []

    def test_missing_fields_detected(self):
        schema = get_schema()
        errors = validate_essay(FIXTURES / "missing-field.md", schema)
        # Missing: excerpt, portfolio_relevance, related_repos, reading_time, word_count
        # Also tags has only 1 item (min 2)
        assert len(errors) >= 5
        assert any("missing required field" in e for e in errors)

    def test_wrong_enum_detected(self):
        schema = get_schema()
        errors = validate_essay(FIXTURES / "wrong-enum.md", schema)
        assert any("category" in e and "must be one of" in e for e in errors)

    def test_bad_pattern_detected(self):
        schema = get_schema()
        errors = validate_essay(FIXTURES / "bad-pattern.md", schema)
        # author missing @, date wrong format, related_repo wrong pattern, reading_time wrong format
        assert any("author" in e for e in errors)
        assert any("date" in e for e in errors)

    def test_short_excerpt_detected(self):
        schema = get_schema()
        errors = validate_essay(FIXTURES / "short-excerpt.md", schema)
        assert any("excerpt" in e and "too short" in e for e in errors)
