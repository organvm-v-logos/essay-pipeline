# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Packaged the schema-enforced essay templates as a sellable **template library**: a docs catalog (`docs/templates/README.md`), a machine-readable catalog (`templates/manifest.yaml`), one free sample template, and five premium templates (`templates/free/`, `templates/premium/`)
- Added `src/license.py` — offline HMAC-SHA256 license keys (issue/verify CLI, `EPK1.<payload>.<sig>` format) for the one-time-purchase ($49 single / $99 bundle) gate
- Added `src/template_store.py` — licensed storefront CLI (`essay-template list|show|eject`) that serves free templates openly and gates premium ones behind a valid license
- Added `essay-template` and `essay-license` console scripts to `pyproject.toml`
- Added ADR 003 documenting the HMAC licensing decision (`docs/adr/003-template-library-licensing.md`)
- Added `tests/test_license.py` and `tests/test_template_store.py`
- Added template-specific entitlements for `premium-single` license keys so $49
  purchases unlock only the purchased template while `premium-bundle` keys
  unlock the full premium catalog
- Extended `src/topic_suggester.py` with configurable thresholds/limits (`tag-threshold`, `surfaced-threshold`, `max-suggestions`, `per-type-limit`)
- Added suggestion ranking pipeline: score normalization, priority buckets, effort estimates, deduplication, per-type balancing, and stable rank assignment
- Added corpus-aware helpers for tag co-occurrence and companion-tag inference to enrich suggestion payloads
- Added richer output metadata: `configuration`, `diagnostics`, suggestion mix summary, and per-suggestion structured fields (`id`, `score`, `focus_area`, `priority_reason`, `estimated_effort`, `rank`)

### Changed

- Bumped topic suggester pipeline version from `0.3.0` to `0.4.0`
- Expanded `tests/test_topic_suggester.py` to cover the full suggestion engine surface (21 tests)

## [0.2.0] - 2026-02-24

### Added

- `src/topic_suggester.py` — analyzes corpus for under-covered tags, underserved categories, surfaced articles, and orphan essays to generate essay topic suggestions (`essay-topic-suggestions` produce edge)
- `src/sprint_narrator.py` — combines analytics metrics, GitHub activity, essay stats, and publication cadence into a markdown sprint narrative (`sprint-narrative-draft` produce edge)
- Test suites for both new modules (~40 tests)
- Test fixtures: mini JSON datasets for topic suggester and sprint narrator
- CLI entry points: `essay-suggest` and `essay-narrate`
- Ruff linting in CI workflow

### Changed

- Bumped version to 0.2.0
- Updated pyproject.toml description to reflect expanded capabilities

## [0.1.0] - 2026-02-17

### Added

- Initial creation as part of ORGAN-V LOGOS Infrastructure Campaign
- Core project structure and documentation
- README with portfolio-quality documentation

[Unreleased]: https://github.com/organvm-v-logos/essay-pipeline/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/organvm-v-logos/essay-pipeline/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/organvm-v-logos/essay-pipeline/releases/tag/v0.1.0
