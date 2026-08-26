"""Status and usage dashboard for essay-pipeline.

Aggregates the JSON artifacts produced by the pipeline into a compact CLI
dashboard. Missing inputs are tolerated so the command can run in partial CI
contexts while still making gaps visible.

CLI:
    python -m src.dashboard --data-dir data/
    python -m src.dashboard --format json --output dashboard.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PIPELINE_VERSION = "0.1.0"

DEFAULT_FILENAMES = {
    "essays_index": "essays-index.json",
    "publication_calendar": "publication-calendar.json",
    "topic_suggestions": "topic-suggestions.json",
    "engagement_metrics": "engagement-metrics.json",
    "system_report": "system-engagement-report.json",
    "logs_index": "logs-index.json",
}

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _to_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    counts = {}
    for key, count in value.items():
        label = str(key).strip()
        if label:
            counts[label] = _to_int(count)
    return counts


def _top_counts(value: dict[str, int], limit: int = 5) -> list[dict[str, int | str]]:
    items = sorted(value.items(), key=lambda item: (-item[1], item[0]))
    return [{"name": name, "count": count} for name, count in items[:limit]]


def _ordered_counter(
    values: list[str], order: dict[str, int] | None = None
) -> dict[str, int]:
    counts = Counter(values)
    if order:
        items = sorted(counts.items(), key=lambda item: (order.get(item[0], 99), item[0]))
    else:
        items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return dict(items)


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def load_json(path: Path | str) -> tuple[Any, str, str | None]:
    """Load JSON and return ``(data, state, error)``.

    ``state`` is one of: ``ok``, ``missing``, ``invalid``, or ``unreadable``.
    """
    p = Path(path)
    if not p.exists():
        return {}, "missing", None
    try:
        return json.loads(p.read_text(encoding="utf-8")), "ok", None
    except json.JSONDecodeError as exc:
        return {}, "invalid", str(exc)
    except OSError as exc:
        return {}, "unreadable", str(exc)


def build_corpus_summary(index: dict, logs_index: dict | None = None) -> dict:
    """Summarize indexed essay and log corpus data."""
    index = _as_dict(index)
    logs_index = _as_dict(logs_index)
    essays = _as_list(index.get("essays"))

    total_essays = _to_int(index.get("total_essays"), len(essays))
    total_words = _to_int(
        index.get("total_words"),
        sum(_to_int(entry.get("word_count")) for entry in essays if isinstance(entry, dict)),
    )
    avg_words = round(total_words / total_essays) if total_essays else 0
    categories = _clean_count_map(index.get("categories"))
    top_category = _top_counts(categories, limit=1)

    return {
        "available": bool(index),
        "updated": index.get("updated", ""),
        "total_essays": total_essays,
        "total_words": total_words,
        "average_words_per_essay": avg_words,
        "category_count": len(categories),
        "top_category": top_category[0] if top_category else None,
        "top_tags": _top_counts(_clean_count_map(index.get("tag_frequency")), limit=5),
        "total_logs": _to_int(logs_index.get("total_logs")),
        "total_log_words": _to_int(logs_index.get("total_words")),
    }


def _calendar_dates(calendar: dict) -> dict[str, int]:
    """Return publication dates from either historical or current calendar shape."""
    calendar = _as_dict(calendar)
    dates = calendar.get("dates")
    if not isinstance(dates, dict):
        dates = calendar.get("essays")
    return _clean_count_map(dates)


def build_publication_summary(calendar: dict) -> dict:
    """Summarize publication cadence."""
    calendar = _as_dict(calendar)
    dates = _calendar_dates(calendar)
    sorted_dates = sorted(dates)
    busiest = None
    if dates:
        day, count = max(dates.items(), key=lambda item: (item[1], item[0]))
        busiest = {"date": day, "count": count}

    return {
        "available": bool(calendar),
        "updated": calendar.get("updated", ""),
        "total_essays": _to_int(calendar.get("total_essays"), sum(dates.values())),
        "total_logs": _to_int(calendar.get("total_logs")),
        "distinct_publication_days": len(dates),
        "first_date": sorted_dates[0] if sorted_dates else "",
        "latest_date": sorted_dates[-1] if sorted_dates else "",
        "busiest_day": busiest,
    }


def build_suggestion_summary(suggestions: dict | list) -> dict:
    """Summarize topic suggestion volume and mix."""
    if isinstance(suggestions, list):
        items = [item for item in suggestions if isinstance(item, dict)]
        generated_at = ""
        available = True
    else:
        data = _as_dict(suggestions)
        items = [item for item in _as_list(data.get("suggestions")) if isinstance(item, dict)]
        generated_at = data.get("generated_at", "")
        available = bool(data)

    priorities = [str(item.get("priority", "unknown") or "unknown") for item in items]
    types = [str(item.get("type", "unknown") or "unknown") for item in items]

    def sort_key(item: dict) -> tuple[int, float, str]:
        priority = str(item.get("priority", "unknown") or "unknown")
        return (
            PRIORITY_ORDER.get(priority, 99),
            -_to_float(item.get("score")),
            str(item.get("title", "")),
        )

    top_items = []
    for item in sorted(items, key=sort_key)[:5]:
        top_items.append(
            {
                "title": str(item.get("title", "")),
                "type": str(item.get("type", "")),
                "priority": str(item.get("priority", "")),
                "score": _to_float(item.get("score")),
            }
        )

    total = len(items)
    if isinstance(suggestions, dict):
        total = _to_int(suggestions.get("total_suggestions"), total)

    priority_counts = _ordered_counter(priorities, PRIORITY_ORDER)

    return {
        "available": available,
        "generated_at": generated_at,
        "total_suggestions": total,
        "by_priority": priority_counts,
        "by_type": _ordered_counter(types),
        "high_attention_count": priority_counts.get("critical", 0)
        + priority_counts.get("high", 0),
        "top_suggestions": top_items,
    }


def build_usage_summary(metrics: dict, report: dict | None = None) -> dict:
    """Summarize public-process usage from engagement metrics or report fallback."""
    metrics = _as_dict(metrics)
    report = _as_dict(report)
    totals = _as_dict(metrics.get("site_totals"))
    web = _as_dict(report.get("web_engagement"))
    pages = [page for page in _as_list(metrics.get("pages")) if isinstance(page, dict)]
    trends = _as_dict(metrics.get("trends"))

    source = "engagement_metrics" if totals else "system_report" if web else ""
    page_views = _to_int(totals.get("page_views"), _to_int(web.get("total_views")))
    visitors = _to_int(totals.get("unique_visitors"), _to_int(web.get("total_visitors")))
    top_page = None
    if pages:
        page = max(pages, key=lambda item: _to_int(item.get("views")))
        top_page = {
            "path": str(page.get("path", "")),
            "views": _to_int(page.get("views")),
            "visitors": _to_int(page.get("visitors")),
        }
    elif web.get("top_essay"):
        top_page = {"path": str(web.get("top_essay")), "views": 0, "visitors": 0}

    return {
        "available": bool(totals or web),
        "source": source,
        "generated_at": metrics.get("generated_at") or report.get("generated_at", ""),
        "period": metrics.get("period") or report.get("period") or {},
        "page_views": page_views,
        "unique_visitors": visitors,
        "referrer_count": _to_int(totals.get("referrer_count")),
        "views_delta_pct": trends.get("views_delta_pct"),
        "visitors_delta_pct": trends.get("visitors_delta_pct"),
        "top_page": top_page,
    }


def build_activity_summary(report: dict) -> dict:
    """Summarize cross-organ development activity."""
    report = _as_dict(report)
    gh = _as_dict(report.get("github_activity"))
    breakdown = _as_dict(gh.get("organ_breakdown"))
    top_organs = []
    for organ, stats in breakdown.items():
        stats = _as_dict(stats)
        top_organs.append(
            {
                "organ": str(organ),
                "commits": _to_int(stats.get("commits")),
                "prs": _to_int(stats.get("prs")),
                "releases": _to_int(stats.get("releases")),
            }
        )
    top_organs.sort(key=lambda item: (-item["commits"], item["organ"]))

    return {
        "available": bool(gh),
        "total_commits": _to_int(gh.get("total_commits")),
        "total_prs": _to_int(gh.get("total_prs")),
        "total_releases": _to_int(gh.get("total_releases")),
        "top_organs": top_organs[:5],
    }


def build_alert_summary(report: dict) -> dict:
    """Summarize system alerts from the engagement report."""
    report = _as_dict(report)
    items = []
    for alert in _as_list(report.get("alerts")):
        if not isinstance(alert, dict):
            continue
        items.append(
            {
                "severity": str(alert.get("severity", "info") or "info"),
                "rule": str(alert.get("rule", "unknown") or "unknown"),
                "description": str(alert.get("description", "")),
                "current_value": alert.get("current_value"),
                "threshold": alert.get("threshold"),
                "triggered_at": str(alert.get("triggered_at", "")),
            }
        )

    highest = ""
    if items:
        highest = sorted(
            [item["severity"] for item in items],
            key=lambda severity: SEVERITY_ORDER.get(severity, 99),
        )[0]

    return {
        "count": len(items),
        "highest_severity": highest,
        "by_severity": _ordered_counter(
            [item["severity"] for item in items], SEVERITY_ORDER
        ),
        "items": items,
    }


def build_status_summary(
    sources: list[dict],
    alerts: dict,
    availability: dict[str, bool],
) -> dict:
    """Build the top-level health summary."""
    invalid_sources = [
        source for source in sources if source.get("state") in {"invalid", "unreadable"}
    ]
    missing_sources = [
        source
        for source in sources
        if source.get("state") == "missing" and not source.get("optional")
    ]
    unavailable = [name for name, available in availability.items() if not available]
    highest = alerts.get("highest_severity", "")

    if invalid_sources or highest == "critical":
        health = "degraded"
    elif highest == "warning":
        health = "attention"
    elif unavailable:
        health = "partial"
    else:
        health = "ok"

    messages = []
    if invalid_sources:
        messages.append(f"{len(invalid_sources)} input artifact(s) invalid or unreadable")
    if missing_sources:
        messages.append(f"{len(missing_sources)} input artifact(s) missing")
    if unavailable:
        messages.append(f"Unavailable dashboard section(s): {', '.join(unavailable)}")
    if alerts.get("count"):
        messages.append(
            f"{alerts['count']} alert(s), highest severity: {highest or 'unknown'}"
        )
    if not messages:
        messages.append("All dashboard inputs available and no alerts reported")

    return {
        "health": health,
        "messages": messages,
        "missing_inputs": [source["name"] for source in missing_sources],
        "invalid_inputs": [source["name"] for source in invalid_sources],
        "unavailable_sections": unavailable,
    }


def build_dashboard(
    index: dict,
    calendar: dict,
    suggestions: dict | list,
    metrics: dict,
    report: dict,
    logs_index: dict | None = None,
    sources: list[dict] | None = None,
) -> dict:
    """Build the full dashboard data structure."""
    corpus = build_corpus_summary(index, logs_index)
    publication = build_publication_summary(calendar)
    suggestion_summary = build_suggestion_summary(suggestions)
    usage = build_usage_summary(metrics, report)
    activity = build_activity_summary(report)
    alerts = build_alert_summary(report)
    availability = {
        "corpus": corpus["available"],
        "publication": publication["available"],
        "suggestions": suggestion_summary["available"],
        "usage": usage["available"],
        "activity": activity["available"],
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dashboard_version": PIPELINE_VERSION,
        "status": build_status_summary(sources or [], alerts, availability),
        "corpus": corpus,
        "publication": publication,
        "suggestions": suggestion_summary,
        "usage": usage,
        "activity": activity,
        "alerts": alerts,
        "sources": sources or [],
    }


def _resolve_path(data_dir: Path, override: str | None, filename: str) -> Path:
    return Path(override) if override else data_dir / filename


def collect_dashboard(
    data_dir: str | Path = "data",
    index_path: str | None = None,
    calendar_path: str | None = None,
    suggestions_path: str | None = None,
    metrics_path: str | None = None,
    report_path: str | None = None,
    logs_index_path: str | None = None,
) -> dict:
    """Load configured artifacts and build dashboard data."""
    data_dir_path = Path(data_dir)
    paths = {
        "essays_index": _resolve_path(
            data_dir_path, index_path, DEFAULT_FILENAMES["essays_index"]
        ),
        "publication_calendar": _resolve_path(
            data_dir_path, calendar_path, DEFAULT_FILENAMES["publication_calendar"]
        ),
        "topic_suggestions": _resolve_path(
            data_dir_path, suggestions_path, DEFAULT_FILENAMES["topic_suggestions"]
        ),
        "engagement_metrics": _resolve_path(
            data_dir_path, metrics_path, DEFAULT_FILENAMES["engagement_metrics"]
        ),
        "system_report": _resolve_path(
            data_dir_path, report_path, DEFAULT_FILENAMES["system_report"]
        ),
        "logs_index": _resolve_path(
            data_dir_path, logs_index_path, DEFAULT_FILENAMES["logs_index"]
        ),
    }

    loaded: dict[str, Any] = {}
    sources = []
    for name, path in paths.items():
        data, state, error = load_json(path)
        loaded[name] = data
        sources.append(
            {
                "name": name,
                "path": str(path),
                "state": state,
                "error": error,
                "optional": name == "logs_index",
            }
        )

    return build_dashboard(
        loaded["essays_index"],
        loaded["publication_calendar"],
        loaded["topic_suggestions"],
        loaded["engagement_metrics"],
        loaded["system_report"],
        logs_index=loaded["logs_index"],
        sources=sources,
    )


def _fmt_int(value: Any) -> str:
    return f"{_to_int(value):,}"


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{_to_float(value):+.1f}%"


def _count_list(items: list[dict], empty: str = "none") -> str:
    if not items:
        return empty
    return ", ".join(f"{item['name']} ({item['count']})" for item in items)


def render_text(dashboard: dict) -> str:
    """Render dashboard data as a compact terminal report."""
    status = dashboard["status"]
    corpus = dashboard["corpus"]
    publication = dashboard["publication"]
    suggestions = dashboard["suggestions"]
    usage = dashboard["usage"]
    activity = dashboard["activity"]
    alerts = dashboard["alerts"]

    lines = [
        "Essay Pipeline Dashboard",
        f"Generated: {dashboard['generated_at']}",
        f"Status: {status['health']}",
    ]
    lines.extend(f"  - {message}" for message in status["messages"])
    lines.append("")

    lines.extend(
        [
            "Corpus",
            f"  Essays: {_fmt_int(corpus['total_essays'])}",
            f"  Words: {_fmt_int(corpus['total_words'])}",
            f"  Average words per essay: {_fmt_int(corpus['average_words_per_essay'])}",
            f"  Categories: {_fmt_int(corpus['category_count'])}",
            f"  Top category: "
            f"{corpus['top_category']['name']} ({corpus['top_category']['count']})"
            if corpus["top_category"]
            else "  Top category: none",
            f"  Top tags: {_count_list(corpus['top_tags'])}",
            f"  Logs: {_fmt_int(corpus['total_logs'])}",
            "",
        ]
    )

    if publication["distinct_publication_days"]:
        busiest = publication["busiest_day"] or {}
        lines.extend(
            [
                "Publication",
                f"  Distinct days: {_fmt_int(publication['distinct_publication_days'])}",
                f"  Date range: {publication['first_date']} to {publication['latest_date']}",
                f"  Busiest day: {busiest.get('date', '')} ({busiest.get('count', 0)})",
                "",
            ]
        )
    else:
        lines.extend(["Publication", "  No publication calendar data available.", ""])

    priority_mix = (
        ", ".join(
            f"{key} ({value})" for key, value in suggestions["by_priority"].items()
        )
        or "none"
    )
    type_mix = (
        ", ".join(f"{key} ({value})" for key, value in suggestions["by_type"].items())
        or "none"
    )
    lines.extend(
        [
            "Suggestions",
            f"  Total: {_fmt_int(suggestions['total_suggestions'])}",
            f"  High attention: {_fmt_int(suggestions['high_attention_count'])}",
            f"  By priority: {priority_mix}",
            f"  By type: {type_mix}",
        ]
    )
    for item in suggestions["top_suggestions"][:3]:
        lines.append(
            f"  - [{item['priority'] or 'unknown'}] {item['title']} ({item['type']})"
        )
    lines.append("")

    if usage["available"]:
        top_page = usage["top_page"] or {}
        page_views = (
            f"  Page views: {_fmt_int(usage['page_views'])} "
            f"({_fmt_pct(usage['views_delta_pct'])})"
        )
        unique_visitors = (
            f"  Unique visitors: {_fmt_int(usage['unique_visitors'])} "
            f"({_fmt_pct(usage['visitors_delta_pct'])})"
        )
        top_page_line = (
            f"  Top page: {top_page.get('path', 'n/a')} "
            f"({_fmt_int(top_page.get('views'))} views)"
        )
        lines.extend(
            [
                "Usage",
                page_views,
                unique_visitors,
                f"  Referrers: {_fmt_int(usage['referrer_count'])}",
                top_page_line,
                "",
            ]
        )
    else:
        lines.extend(["Usage", "  No engagement metrics available.", ""])

    if activity["available"]:
        top_organs = ", ".join(
            f"{item['organ']} ({item['commits']})" for item in activity["top_organs"]
        )
        lines.extend(
            [
                "Activity",
                f"  Commits: {_fmt_int(activity['total_commits'])}",
                f"  PRs: {_fmt_int(activity['total_prs'])}",
                f"  Releases: {_fmt_int(activity['total_releases'])}",
                f"  Top organs by commits: {top_organs or 'none'}",
                "",
            ]
        )
    else:
        lines.extend(["Activity", "  No system activity report available.", ""])

    lines.append("Alerts")
    if alerts["items"]:
        for alert in alerts["items"]:
            lines.append(
                f"  - {alert['severity'].upper()} {alert['rule']}: "
                f"{alert['description']}"
            )
    else:
        lines.append("  No alerts reported.")

    return "\n".join(lines) + "\n"


def render_json(dashboard: dict) -> str:
    """Render dashboard data as stable JSON."""
    return json.dumps(dashboard, indent=2, ensure_ascii=False) + "\n"


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Show essay-pipeline status and usage metrics"
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory containing generated data artifacts (default: data)",
    )
    parser.add_argument("--index", default=None, help="Path to essays-index.json")
    parser.add_argument(
        "--calendar", default=None, help="Path to publication-calendar.json"
    )
    parser.add_argument(
        "--suggestions", default=None, help="Path to topic-suggestions.json"
    )
    parser.add_argument(
        "--metrics", default=None, help="Path to engagement-metrics.json"
    )
    parser.add_argument(
        "--report", default=None, help="Path to system-engagement-report.json"
    )
    parser.add_argument("--logs-index", default=None, help="Path to logs-index.json")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Dashboard output format",
    )
    parser.add_argument("--output", default=None, help="Write dashboard to this path")
    args = parser.parse_args(argv)

    dashboard = collect_dashboard(
        data_dir=args.data_dir,
        index_path=args.index,
        calendar_path=args.calendar,
        suggestions_path=args.suggestions,
        metrics_path=args.metrics,
        report_path=args.report,
        logs_index_path=args.logs_index,
    )
    rendered = render_json(dashboard) if args.format == "json" else render_text(dashboard)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered, encoding="utf-8")
        print(f"Wrote dashboard -> {out}")
    else:
        print(rendered, end="")

    return 0


def main() -> None:
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
