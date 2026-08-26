"""Licensed catalog of essay templates (the sellable template library).

The store reads ``templates/manifest.yaml`` and serves template bodies. Free
templates are readable by anyone; premium templates are gated behind a valid
HMAC license key (see :mod:`src.license`). This is the storefront layer that
turns the schema-enforced templates into a one-time-purchase product.

CLI:
    python -m src.template_store list [--license KEY]
    python -m src.template_store show <id> [--license KEY]
    python -m src.template_store eject <id> --output path/to/new-essay.md --license KEY
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from .license import LicenseError, verify_license

# templates/ lives at the repo root, one level up from src/.
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
MANIFEST_NAME = "manifest.yaml"


class TemplateError(Exception):
    """Base class for template-store failures."""


class TemplateNotFound(TemplateError):
    """Raised when a template id is not in the catalog."""


class LicenseRequired(TemplateError):
    """Raised when a premium template is requested without a valid license."""


@dataclass(frozen=True)
class TemplateEntry:
    """One catalog entry resolved from the manifest."""

    id: str
    tier: str
    path: str
    title: str
    summary: str
    best_for: str

    @property
    def is_premium(self) -> bool:
        return self.tier == "premium"


def load_manifest(templates_dir: Path | str | None = None) -> dict:
    """Load and minimally validate the catalog manifest."""
    base = Path(templates_dir) if templates_dir else TEMPLATES_DIR
    manifest_path = base / MANIFEST_NAME
    if not manifest_path.exists():
        raise TemplateError(f"Manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        manifest = yaml.safe_load(f)

    if not isinstance(manifest, dict) or "templates" not in manifest:
        raise TemplateError(f"Manifest missing 'templates' key: {manifest_path}")
    return manifest


def list_templates(templates_dir: Path | str | None = None) -> list[TemplateEntry]:
    """Return all catalog entries."""
    manifest = load_manifest(templates_dir)
    entries = []
    for raw in manifest["templates"]:
        entries.append(
            TemplateEntry(
                id=raw["id"],
                tier=raw.get("tier", "premium"),
                path=raw["path"],
                title=raw.get("title", raw["id"]),
                summary=raw.get("summary", ""),
                best_for=raw.get("best_for", ""),
            )
        )
    return entries


def get_entry(template_id: str, templates_dir: Path | str | None = None) -> TemplateEntry:
    """Look up a single catalog entry by id."""
    for entry in list_templates(templates_dir):
        if entry.id == template_id:
            return entry
    raise TemplateNotFound(f"No template with id '{template_id}' in catalog")


def is_unlocked(
    entry: TemplateEntry,
    license_key: str | None = None,
    secret: bytes | str | None = None,
) -> bool:
    """Whether `entry` is accessible given (or lacking) a license key."""
    if not entry.is_premium:
        return True
    return _license_grants_template(license_key, entry.id, secret)


def _license_grants_template(
    license_key: str | None, template_id: str, secret: bytes | str | None
) -> bool:
    if not license_key:
        return False
    try:
        return verify_license(license_key, secret).covers_template(template_id)
    except LicenseError:
        return False


def read_template(
    template_id: str,
    license_key: str | None = None,
    templates_dir: Path | str | None = None,
    secret: bytes | str | None = None,
) -> str:
    """Return a template's body, enforcing the license gate for premium ones.

    Raises:
        TemplateNotFound: Unknown template id.
        LicenseRequired: Premium template requested without a valid license.
        TemplateError: Template file missing on disk.
    """
    base = Path(templates_dir) if templates_dir else TEMPLATES_DIR
    entry = get_entry(template_id, base)

    if entry.is_premium and not _license_grants_template(license_key, entry.id, secret):
        raise LicenseRequired(
            f"'{template_id}' is a premium template. Provide a valid premium-bundle "
            f"key or a premium-single key for this template "
            f"(buy at the catalog in docs/templates/README.md, then pass --license)."
        )

    template_path = base / entry.path
    if not template_path.exists():
        raise TemplateError(f"Template file missing: {template_path}")
    return template_path.read_text(encoding="utf-8")


def _cmd_list(args: argparse.Namespace) -> int:
    entries = list_templates()
    locked_premium = []
    print(f"{'ID':<22} {'TIER':<8} {'ACCESS':<10} TITLE")
    print("-" * 72)
    for entry in entries:
        unlocked = is_unlocked(entry, args.license)
        access = "open" if unlocked else "locked"
        if entry.is_premium and unlocked:
            access = "unlocked"
        if entry.is_premium and not unlocked:
            locked_premium.append(entry.id)
        print(f"{entry.id:<22} {entry.tier:<8} {access:<10} {entry.title}")
        if entry.summary:
            print(f"{'':<22} {'':<8} {'':<10} {entry.summary}")

    if locked_premium and args.license:
        print(
            "\nSome premium templates are locked. Use a premium-bundle key "
            "or a matching premium-single key."
        )
    elif locked_premium:
        print("\nPremium templates are locked. See docs/templates/README.md to purchase.")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        body = read_template(args.id, license_key=args.license)
    except LicenseRequired as exc:
        print(f"LOCKED — {exc}", file=sys.stderr)
        return 2
    except TemplateNotFound as exc:
        print(f"NOT FOUND — {exc}", file=sys.stderr)
        return 1
    print(body)
    return 0


def _cmd_eject(args: argparse.Namespace) -> int:
    try:
        body = read_template(args.id, license_key=args.license)
    except LicenseRequired as exc:
        print(f"LOCKED — {exc}", file=sys.stderr)
        return 2
    except TemplateNotFound as exc:
        print(f"NOT FOUND — {exc}", file=sys.stderr)
        return 1

    out = Path(args.output)
    if out.exists() and not args.force:
        print(f"REFUSING — {out} exists (use --force to overwrite)", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    print(f"Wrote {args.id} → {out}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse and unlock essay templates")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List the catalog")
    p_list.add_argument("--license", default=None, help="License key (unlocks premium)")
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="Print a template to stdout")
    p_show.add_argument("id", help="Template id")
    p_show.add_argument("--license", default=None, help="License key (required for premium)")
    p_show.set_defaults(func=_cmd_show)

    p_eject = sub.add_parser("eject", help="Copy a template to a new file")
    p_eject.add_argument("id", help="Template id")
    p_eject.add_argument("--output", required=True, help="Destination path")
    p_eject.add_argument("--license", default=None, help="License key (required for premium)")
    p_eject.add_argument("--force", action="store_true", help="Overwrite existing file")
    p_eject.set_defaults(func=_cmd_eject)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
