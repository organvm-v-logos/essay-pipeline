# ADR 001: Initial Architecture Decisions

## Status

Accepted

## Date

2026-02-17

## Context

essay-pipeline is the automation engine behind ORGAN-V's public-process discourse layer. We need to make foundational decisions about the programming language, orchestration platform, and data interchange format before building any components. These decisions will constrain the system for its entire lifecycle, so they must account for the existing organvm ecosystem, the skill set of contributors, and the operational environment (GitHub-hosted, CI-driven, no persistent infrastructure).

The pipeline must:

1. Scan 8 GitHub organizations for activity via the GitHub REST/GraphQL API
2. Generate structured Markdown documents (sprint narratives, topic suggestions)
3. Validate YAML frontmatter in Markdown files against a strict schema
4. Produce and consume JSON index files
5. Run reliably in GitHub Actions with minimal dependencies
6. Be maintainable by a solo developer with occasional AI-assisted contributions

### Options Considered

**Programming Language**

- **Python**: Mature GitHub API libraries (PyGithub, ghapi), excellent YAML/JSON handling, Jinja2 for templating, strong ecosystem for text processing. Already used in ORGAN-IV orchestration scripts (organ-audit.py, validate-deps.py, calculate-metrics.py).
- **TypeScript/Node.js**: Good GitHub API support (octokit), strong typing, native JSON handling. Used in some ORGAN-III frontend projects.
- **Shell (bash)**: Zero dependencies in CI, but fragile for complex data processing, poor error handling, no typing, difficult to test.
- **Go**: Fast, single-binary deployment, good GitHub API library. Not currently used elsewhere in the organvm system.

**Orchestration Platform**

- **GitHub Actions**: Already used across all 8 organs. Zero additional infrastructure. Native integration with GitHub API, secrets, and event triggers.
- **Self-hosted CI (Jenkins, Drone)**: More control but requires infrastructure management. Contradicts the project's zero-infrastructure principle.
- **Cron on a VPS**: Simple but introduces a single point of failure outside GitHub. Secrets management becomes a separate concern.

**Data Interchange Format**

- **JSON**: Universal support, native to GitHub API responses, parseable in every language, supported by Jekyll's data files. Slightly verbose for human reading.
- **YAML**: More human-readable, native format for frontmatter. But introduces ambiguity (the Norway problem, implicit type coercion) and is slower to parse than JSON.
- **SQLite**: Structured queries, ACID guarantees. But adds a binary file to the repo, complicates diffing, and is overkill for the data volume (fewer than 1,000 essays projected).
- **CSV**: Simple but loses hierarchical structure. Inadequate for nested metadata.

## Decision

1. **Python 3.11+** as the implementation language
2. **GitHub Actions** as the orchestration platform
3. **JSON** as the data interchange format for machine-readable artifacts (essays-index.json, topic scores, metrics); **YAML** retained only for human-authored frontmatter in essays

## Rationale

**Python** wins on ecosystem alignment. The ORGAN-IV orchestration scripts are already Python. PyGithub and Jinja2 are battle-tested for exactly this use case. Python's `yaml` and `json` standard/near-standard libraries handle all data formats. Type hints (PEP 484) provide sufficient safety for a project of this scale without the ceremony of a compiled language. The solo-developer constraint favors a language where iteration speed is high.

**GitHub Actions** wins on zero-infrastructure. The entire organvm system already runs on GitHub. Actions provides cron scheduling, event-driven triggers (push, repository_dispatch), secrets management, and artifact storage. There is no operational burden -- no servers to patch, no uptime to monitor. The tradeoff is vendor lock-in to GitHub, which is acceptable given that the entire eight-organ system is already GitHub-native.

**JSON** wins for machine-readable interchange because it eliminates the YAML ambiguity problem. When the monitor scores events or the indexer catalogs essays, the data must be unambiguous. JSON's strict typing (strings are always strings, numbers are always numbers) prevents the class of bugs where YAML silently coerces `NO` to `false` or `3.10` to `3.1`. YAML is retained for frontmatter because essays are human-authored and YAML's readability advantage matters there -- but the validator converts frontmatter to a Python dict immediately and validates against typed rules, so YAML's ambiguities are caught before they propagate.

## Consequences

### Positive

- Consistent language choice across ORGAN-IV and ORGAN-V automation scripts
- Zero infrastructure to manage; pipeline runs entirely within GitHub's free tier
- JSON index files are trivially consumable by Jekyll (via `_data/`) and by any future frontend
- Python's ecosystem provides libraries for every pipeline stage without custom implementations

### Negative

- Python is slower than Go or Rust for API-heavy workloads, but the pipeline processes fewer than 100 repos and fewer than 1,000 essays, so performance is irrelevant at this scale
- GitHub Actions has a 6-hour job timeout and limited concurrency on free tier; the pipeline must complete within these constraints
- JSON lacks comments, so any inline documentation of the index format must live in this ADR or the README, not in the data files themselves

### Risks

- If the organvm system grows beyond GitHub (e.g., self-hosted Gitea), the GitHub Actions dependency becomes a migration obstacle. Mitigation: keep GitHub-specific API calls isolated in `src/monitor.py` behind an abstract interface.
- If Python 3.11 features are used (e.g., `tomllib`), CI runners must be pinned to 3.11+. Mitigation: use `setup-python@v5` with explicit version pinning in workflows.
