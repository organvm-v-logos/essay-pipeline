# ADR 002: Frontmatter Schema Design

## Status

Accepted

## Date

2026-02-17

## Context

Every essay published through ORGAN-V's public-process must include YAML frontmatter that drives Jekyll rendering, essay indexing, cross-referencing, and feed generation. Without a formal schema, frontmatter fields drift over time: authors add ad-hoc fields, misspell existing ones, omit required metadata, or use inconsistent formats. This drift breaks the indexer, produces malformed RSS feeds, and makes the essay corpus unreliable as a structured dataset.

We need a schema definition that:

1. Defines every allowed field, its type, and its constraints
2. Is machine-readable so the validator can enforce it automatically
3. Is human-readable so authors can reference it while writing
4. Supports evolution (adding new fields) without breaking existing essays
5. Catches errors before they reach the Jekyll build

### Schema Definition Options

**Option A: JSON Schema**
The industry standard for schema validation. Rich type system, conditional logic (`if/then/else`), pattern matching, and a massive ecosystem of validators in every language. However, JSON Schema files are verbose and difficult for non-specialists to read. The schema for 11 frontmatter fields would be 150+ lines of JSON, most of it boilerplate.

**Option B: YAML Schema (custom)**
Define the schema in YAML (matching the frontmatter format) with a custom Python validator. The schema file reads like annotated frontmatter -- authors can understand it without learning JSON Schema syntax. Validation logic lives in Python code rather than in the schema language, which means more flexibility but also more code to maintain.

**Option C: Pydantic Model**
Define the schema as a Python Pydantic model. Excellent validation with clear error messages. Type safety is built in. However, the schema lives in Python code, not in a standalone file. Non-Python contributors cannot read or modify the schema without understanding Python. Also couples the schema definition to a specific library version.

**Option D: No Schema (convention-only)**
Document the expected fields in the README and trust authors to follow the convention. Zero tooling overhead. But conventions decay without enforcement, especially in a system that may be maintained by AI agents that need explicit schemas to operate correctly.

### Field Selection Rationale

The specific fields in the schema were chosen based on the requirements of four consumers:

1. **Jekyll**: Needs `layout`, `title`, `date`, `author`, `tags` for rendering
2. **Indexer**: Needs all Jekyll fields plus `abstract`, `organ`, `status` for the JSON catalog
3. **Feed generator**: Needs `title`, `date`, `author`, `abstract` for Atom entries
4. **Cross-referencing**: Needs `organ`, `sprint`, `series`, `series_order` to link essays to system components and to each other

Fields not included (and why):

- `permalink`: Derived from `date` and title slug; storing it would create a sync risk
- `excerpt`: Jekyll auto-generates from first paragraph; `abstract` serves the same purpose with explicit control
- `image`: No image support in current site design; would add complexity for no benefit
- `categories`: Tags serve this purpose; categories in Jekyll create URL path segments which we want to control via `organ` instead

## Decision

**Option B: YAML schema with Python validation.**

The schema is defined in `schema/frontmatter.yaml` as an annotated YAML document. Each field entry specifies: type, required status, constraints (min/max length, allowed values, regex patterns), and a human-readable description. The Python validator (`src/validator.py`) loads this schema at runtime and validates each essay's frontmatter against it.

Unknown fields are rejected by default. This is a deliberate strictness choice: it prevents frontmatter drift and forces every new field through the ADR process. If a field needs to be added, the process is: write an ADR, update the schema file, update the validator if needed, update the README.

### Schema Definition Format

```yaml
# schema/frontmatter.yaml
fields:
  layout:
    type: string
    required: true
    allowed: ["post"]
    description: "Page layout template. Must be 'post' for essays."

  title:
    type: string
    required: true
    min_length: 10
    max_length: 200
    description: "Essay title. Used in HTML title, feed entries, and index."

  date:
    type: date
    required: true
    format: "YYYY-MM-DD"
    validate_against_filename: true
    description: "Publication date in ISO 8601. Must match the date prefix in the filename."

  author:
    type: string
    required: true
    description: "GitHub username of the primary author."

  tags:
    type: list
    required: true
    min_items: 1
    max_items: 5
    item_type: string
    description: "Topic tags for categorization. 1-5 tags from controlled vocabulary."

  organ:
    type: string
    required: true
    allowed: ["I", "II", "III", "IV", "V", "VI", "VII", "META"]
    description: "Primary organ this essay relates to. Roman numeral or META."

  sprint:
    type: string
    required: false
    pattern: "^[A-Z][A-Z0-9-]*$"
    description: "Sprint identifier if essay is sprint-related. Uppercase alphanumeric with hyphens."

  series:
    type: string
    required: false
    pattern: "^[a-z][a-z0-9-]*$"
    description: "Series identifier for multi-part essays. Lowercase alphanumeric with hyphens."

  series_order:
    type: integer
    required: false
    required_if: "series"
    min_value: 1
    description: "Position in series. Required if series is set. Integer >= 1."

  abstract:
    type: string
    required: true
    min_length: 50
    max_length: 500
    description: "One-paragraph summary. Used in index, feed, and social sharing."

  status:
    type: enum
    required: true
    allowed: ["draft", "review", "published", "archived"]
    description: "Publication status. Only 'published' essays appear on the live site."

strict_mode: true  # Reject unknown fields
```

## Rationale

YAML schema was chosen over JSON Schema because readability wins at this project's scale. The schema has 11 fields. A JSON Schema definition would be syntactically correct but difficult for a solo developer to scan quickly during essay writing. The YAML schema reads like annotated frontmatter -- the format authors are already working in. The cognitive overhead of context-switching between YAML frontmatter and a JSON Schema reference document is non-trivial and unnecessary.

The tradeoff is that validation logic lives in Python code rather than being declaratively expressed in the schema language. This means:

- Conditional requirements (`series_order` required if `series` is set) are implemented in `validator.py`, not in the schema file
- Cross-field validation (date matches filename) is implemented in `validator.py`
- The schema file is documentation + configuration, not a complete executable specification

This tradeoff is acceptable because the validator is approximately 200 lines of Python. The logic is simple enough to audit by reading the code. If the schema grew to 50+ fields with complex conditional logic, JSON Schema's declarative approach would become worthwhile. At 11 fields, Python code is clearer.

Strict mode (rejecting unknown fields) was chosen deliberately to prevent the "frontmatter junk drawer" antipattern. In systems without strict validation, frontmatter accumulates experimental fields that no consumer reads, creating confusion about what is required and what is vestigial. Strict mode makes every field intentional and documented. The cost is a slightly higher barrier to adding new fields, which is desirable -- schema changes should be considered decisions, not accidents.

## Consequences

### Positive

- Authors have a single, readable reference for all frontmatter fields
- The validator catches errors at CI time, before they reach the Jekyll build or the essay index
- Strict mode prevents frontmatter drift and forces deliberate schema evolution
- The YAML format is already familiar to anyone writing essay frontmatter
- Schema changes are tracked in git alongside the code that enforces them

### Negative

- Conditional validation logic is split between the schema file (field definitions) and the validator code (cross-field rules). A developer must read both to understand the complete validation behavior.
- The custom schema format is not interoperable with JSON Schema tooling (editors, auto-complete, external validators). If the ecosystem grows to include non-Python consumers, a JSON Schema export may be needed.
- No schema versioning mechanism is built in. If the schema changes in a way that invalidates existing essays, a migration script will be needed. Mitigation: changes should be additive (new optional fields) whenever possible.

### Future Considerations

- If the essay corpus grows beyond 100 essays, consider generating a JSON Schema from the YAML schema for IDE auto-complete support in VS Code
- If multiple validators are needed (e.g., a pre-commit hook in addition to CI), extract the validation logic into a standalone Python package
- The controlled vocabulary for `tags` should be defined in a separate file (`schema/tags.yaml`) once the tag list stabilizes past 20 entries
