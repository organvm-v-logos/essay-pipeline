"""Tests for the essay-pipeline dashboard."""

import json
from pathlib import Path

from src.dashboard import (
    build_dashboard,
    build_publication_summary,
    collect_dashboard,
    render_json,
    render_text,
    run_cli,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


def _suggestions() -> dict:
    return {
        "generated_at": "2026-02-24T12:00:00+00:00",
        "total_suggestions": 3,
        "suggestions": [
            {
                "title": "Resolve the Governance Gap",
                "type": "tag-gap",
                "priority": "critical",
                "score": 0.91,
            },
            {
                "title": "Follow up on Orphan Essays",
                "type": "cross-ref-gap",
                "priority": "high",
                "score": 0.72,
            },
            {
                "title": "Case Study Backlog",
                "type": "category-gap",
                "priority": "medium",
                "score": 0.45,
            },
        ],
    }


def test_build_dashboard_collects_key_metrics():
    dashboard = build_dashboard(
        _fixture("mini-essays-index.json"),
        _fixture("mini-pub-calendar.json"),
        _suggestions(),
        _fixture("mini-engagement-metrics.json"),
        _fixture("mini-system-report.json"),
    )

    assert dashboard["status"]["health"] == "attention"
    assert dashboard["corpus"]["total_essays"] == 5
    assert dashboard["corpus"]["average_words_per_essay"] == 3000
    assert dashboard["publication"]["latest_date"] == "2026-02-14"
    assert dashboard["suggestions"]["high_attention_count"] == 2
    assert dashboard["usage"]["page_views"] == 1077
    assert dashboard["activity"]["total_commits"] == 45
    assert dashboard["alerts"]["count"] == 1


def test_publication_summary_supports_current_calendar_shape():
    calendar = {
        "total_essays": 3,
        "essays": {"2026-02-10": 1, "2026-02-12": 2},
        "total_logs": 1,
        "logs": {"2026-02-12": 1},
    }

    summary = build_publication_summary(calendar)

    assert summary["distinct_publication_days"] == 2
    assert summary["latest_date"] == "2026-02-12"
    assert summary["busiest_day"] == {"date": "2026-02-12", "count": 2}


def test_render_text_contains_dashboard_sections():
    dashboard = build_dashboard(
        _fixture("mini-essays-index.json"),
        _fixture("mini-pub-calendar.json"),
        _suggestions(),
        _fixture("mini-engagement-metrics.json"),
        _fixture("mini-system-report.json"),
    )

    text = render_text(dashboard)

    assert "Essay Pipeline Dashboard" in text
    assert "Corpus" in text
    assert "Usage" in text
    assert "1,077" in text
    assert "Resolve the Governance Gap" in text


def test_render_json_round_trips():
    dashboard = build_dashboard({}, {}, [], {}, {})

    parsed = json.loads(render_json(dashboard))

    assert parsed["dashboard_version"] == "0.1.0"
    assert parsed["status"]["health"] == "partial"


def test_collect_dashboard_tolerates_missing_inputs(tmp_path):
    dashboard = collect_dashboard(data_dir=tmp_path)

    assert dashboard["status"]["health"] == "partial"
    assert "corpus" in dashboard["status"]["unavailable_sections"]
    assert "essays_index" in dashboard["status"]["missing_inputs"]


def test_run_cli_writes_json_dashboard(tmp_path, capsys):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "essays-index.json").write_text(
        (FIXTURES / "mini-essays-index.json").read_text()
    )
    (data_dir / "publication-calendar.json").write_text(
        (FIXTURES / "mini-pub-calendar.json").read_text()
    )
    (data_dir / "topic-suggestions.json").write_text(json.dumps(_suggestions()))
    (data_dir / "engagement-metrics.json").write_text(
        (FIXTURES / "mini-engagement-metrics.json").read_text()
    )
    (data_dir / "system-engagement-report.json").write_text(
        (FIXTURES / "mini-system-report.json").read_text()
    )
    output = tmp_path / "dashboard.json"

    code = run_cli(["--data-dir", str(data_dir), "--format", "json", "--output", str(output)])

    assert code == 0
    assert "Wrote dashboard" in capsys.readouterr().out
    parsed = json.loads(output.read_text())
    assert parsed["corpus"]["total_essays"] == 5
