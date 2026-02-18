"""Tests for the essay indexer."""

from pathlib import Path

from src.indexer import build_essays_index, build_cross_references, extract_essay_data

FIXTURES = Path(__file__).parent / "fixtures"


class TestExtractEssayData:
    def test_extracts_valid_essay(self):
        data = extract_essay_data(FIXTURES / "valid-essay.md")
        assert data is not None
        assert data["filename"] == "valid-essay.md"
        assert data["frontmatter"]["title"] == "A Perfectly Valid Test Essay for the Pipeline"
        assert data["computed_word_count"] > 0

    def test_no_frontmatter_returns_none(self, tmp_path):
        p = tmp_path / "bare.md"
        p.write_text("Just plain markdown with no frontmatter.")
        assert extract_essay_data(p) is None

    def test_word_count_computation(self):
        data = extract_essay_data(FIXTURES / "valid-essay.md")
        assert data is not None
        # Body has real content — should be at least 40 words
        assert data["computed_word_count"] >= 40


class TestBuildEssaysIndex:
    def test_generates_correct_structure(self):
        essays = [extract_essay_data(FIXTURES / "valid-essay.md")]
        index = build_essays_index(essays)
        assert index["total_essays"] == 1
        assert index["total_words"] > 0
        assert "meta-system" in index["categories"]
        assert "governance" in index["tag_frequency"]
        assert len(index["essays"]) == 1

    def test_handles_zero_essays(self):
        index = build_essays_index([])
        assert index["total_essays"] == 0
        assert index["total_words"] == 0
        assert index["categories"] == {}

    def test_multiple_essays(self):
        essays = []
        for f in FIXTURES.glob("*.md"):
            data = extract_essay_data(f)
            if data:
                essays.append(data)
        index = build_essays_index(essays)
        assert index["total_essays"] == len(essays)
        assert index["total_essays"] >= 3  # We have at least 3 valid fixture files


class TestBuildCrossReferences:
    def test_generates_keyed_entries(self):
        essays = [extract_essay_data(FIXTURES / "valid-essay.md")]
        xrefs = build_cross_references(essays)
        assert xrefs["total"] == 1
        assert "valid-essay.md" in xrefs["entries"]
        entry = xrefs["entries"]["valid-essay.md"]
        assert "organvm-v-logos/essay-pipeline" in entry["related_repos"]
