"""Offline HMAC license keys for the essay-pipeline template library.

A license key is a signed, *readable* token that encodes which product
(sku) was purchased, by whom (email), when (issued), and, for
single-template purchases, which template was bought, or for subscriptions,
when access ends (expires). The signature is an HMAC-SHA256 over that
payload, truncated and base32-encoded.

Verification is fully offline: the same shared secret that signs a key also  # allow-secret
verifies it. This is the classic "HMAC key check" gate — it deters casual
sharing and copying of the premium templates without requiring an activation
server. It is intentionally *not* a DRM system: anyone holding the secret can  # allow-secret
mint keys, so the secret is the asset to protect. Production sellers MUST set  # allow-secret
ESSAY_PIPELINE_LICENSE_SECRET to a private value and issue keys with it;  # allow-secret
the bundled default exists only so the gate is exercisable out of the box.

CLI:
    python -m src.license issue --email buyer@example.com --sku premium-bundle
    python -m src.license issue --email buyer@example.com --sku premium-single --template case-study
    python -m src.license issue --email buyer@example.com --sku premium-subscription --expires 2026-07-19
    python -m src.license verify --key EPK1.<payload>.<sig>
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import sys
from dataclasses import dataclass
from datetime import date

KEY_PREFIX = "EPK1"
SIG_BYTES = 16  # 128-bit truncated HMAC tag; ample for an offline gate
FIELD_SEP = "|"
SEGMENT_SEP = "."

# Demo-only signing secret. Real sellers override via ESSAY_PIPELINE_LICENSE_SECRET.  # allow-secret
DEFAULT_SECRET = b"organvm-essay-pipeline-demo-secret-v1"  # allow-secret

PREMIUM_BUNDLE_SKU = "premium-bundle"
PREMIUM_SINGLE_SKU = "premium-single"
PREMIUM_SUBSCRIPTION_SKU = "premium-subscription"

# SKUs the store knows how to sell. Maps a SKU to the templates it unlocks.
KNOWN_SKUS = {
    PREMIUM_BUNDLE_SKU: "Every premium template in the catalog",
    PREMIUM_SINGLE_SKU: "A single premium template",
    PREMIUM_SUBSCRIPTION_SKU: "Premium access for an active subscription period",
}

SUBSCRIPTION_SKUS = {PREMIUM_SUBSCRIPTION_SKU}


class LicenseError(Exception):
    """Raised when a license key is malformed, tampered with, or unsigned."""


@dataclass(frozen=True)
class License:
    """A verified license payload."""

    sku: str
    email: str
    issued: str
    template_id: str | None = None
    expires: str | None = None

    def covers_premium(self, as_of: date | str | None = None) -> bool:
        """Whether this license grants access to at least one premium template."""
        if self.sku not in KNOWN_SKUS:
            return False
        if self.sku == PREMIUM_SINGLE_SKU:
            return bool(self.template_id)
        if self.sku in SUBSCRIPTION_SKUS and not self.expires:
            return False
        if not self.expires:
            return True

        try:
            expires_on = date.fromisoformat(self.expires)
            check_date = _coerce_date(as_of)
        except ValueError:
            return False
        return check_date <= expires_on

    def covers_template(self, template_id: str, as_of: date | str | None = None) -> bool:
        """Whether this license grants access to a specific premium template."""
        if not self.covers_premium(as_of=as_of):
            return False
        if self.sku == PREMIUM_SINGLE_SKU:
            return self.template_id == template_id
        return True


def _coerce_date(value: date | str | None = None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _get_secret(secret: bytes | str | None = None) -> bytes:  # allow-secret
    if secret is not None:  # allow-secret
        return secret if isinstance(secret, bytes) else secret.encode("utf-8")  # allow-secret
    env_secret = os.environ.get("ESSAY_PIPELINE_LICENSE_SECRET")  # allow-secret
    if env_secret:  # allow-secret
        return env_secret.encode("utf-8")  # allow-secret
    return DEFAULT_SECRET  # allow-secret


def _b32(raw: bytes) -> str:
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _unb32(text: str) -> bytes:
    pad = (-len(text)) % 8
    return base64.b32decode(text.upper() + ("=" * pad))


def _sign(payload: str, secret: bytes) -> bytes:  # allow-secret
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).digest()[:SIG_BYTES]  # allow-secret


def issue_license(
    email: str,
    sku: str = PREMIUM_BUNDLE_SKU,
    issued: str | None = None,
    template_id: str | None = None,
    expires: str | None = None,
    secret: bytes | str | None = None,  # allow-secret
) -> str:
    issued = issued or date.today().isoformat()
    for name, value in {
        "email": email,
        "sku": sku,
        "template_id": template_id,
        "expires": expires,
    }.items():
        if value and FIELD_SEP in value:
            raise LicenseError(f"{name} must not contain {FIELD_SEP!r}")

    if sku == PREMIUM_SINGLE_SKU and not template_id:
        raise LicenseError("premium-single licenses require a template id")
    if template_id and sku != PREMIUM_SINGLE_SKU:
        raise LicenseError("template id can only be used with premium-single licenses")
    if sku in SUBSCRIPTION_SKUS and not expires:
        raise LicenseError("premium-subscription licenses require an expiration date")

    payload = f"{sku}{FIELD_SEP}{email}{FIELD_SEP}{issued}"
    if template_id:
        payload = f"{payload}{FIELD_SEP}{template_id}"
    elif expires:
        payload = f"{payload}{FIELD_SEP}{expires}"

    sig = _sign(payload, _get_secret(secret))  # allow-secret
    return SEGMENT_SEP.join(
        [KEY_PREFIX, _b32(payload.encode("utf-8")), _b32(sig)]
    )


def verify_license(key: str, secret: bytes | str | None = None) -> License:  # allow-secret
    if not isinstance(key, str):
        raise LicenseError("license key must be a string")

    parts = key.strip().split(SEGMENT_SEP)
    if len(parts) != 3 or parts[0] != KEY_PREFIX:
        raise LicenseError("unrecognized license key format")

    _, payload_b32, sig_b32 = parts
    try:
        payload = _unb32(payload_b32).decode("utf-8")
        provided_sig = _unb32(sig_b32)
    except (ValueError, UnicodeDecodeError) as exc:
        raise LicenseError(f"corrupt license key: {exc}") from exc

    expected_sig = _sign(payload, _get_secret(secret))  # allow-secret
    if not hmac.compare_digest(provided_sig, expected_sig):
        raise LicenseError("license signature mismatch (wrong secret or tampered key)")  # allow-secret

    fields = payload.split(FIELD_SEP)
    if len(fields) not in {3, 4}:
        raise LicenseError("license payload has unexpected shape")

    sku, email, issued = fields[:3]
    fourth = fields[3] if len(fields) == 4 else None
    template_id = fourth if sku == PREMIUM_SINGLE_SKU else None
    expires = fourth if sku in SUBSCRIPTION_SKUS or (fourth and not template_id) else None
    return License(sku=sku, email=email, issued=issued, template_id=template_id, expires=expires)


def is_valid(key: str | None, secret: bytes | str | None = None) -> bool:  # allow-secret
    if not key:
        return False
    try:
        verify_license(key, secret)  # allow-secret
        return True
    except LicenseError:
        return False


def _cmd_issue(args: argparse.Namespace) -> int:
    if args.sku not in KNOWN_SKUS:
        print(f"WARNING: '{args.sku}' is not a known SKU {list(KNOWN_SKUS)}", file=sys.stderr)
    try:
        key = issue_license(  # allow-secret
            args.email,
            sku=args.sku,
            issued=args.issued,
            template_id=args.template,
            expires=args.expires,
        )
    except LicenseError as exc:
        print(f"ERROR — {exc}", file=sys.stderr)
        return 2
    print(key)
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    try:
        lic = verify_license(args.key)
    except LicenseError as exc:
        print(f"INVALID — {exc}")
        return 1
    print("VALID")
    print(f"  sku:     {lic.sku}")
    print(f"  email:   {lic.email}")
    print(f"  issued:  {lic.issued}")
    if lic.template_id:
        print(f"  template: {lic.template_id}")
    if lic.expires:
        print(f"  expires: {lic.expires}")
    print(f"  premium access: {'yes' if lic.covers_premium() else 'no'}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Issue and verify essay-pipeline license keys")
    sub = parser.add_subparsers(dest="command", required=True)

    p_issue = sub.add_parser("issue", help="Mint a new license key (seller-side)")
    p_issue.add_argument("--email", required=True, help="Buyer email / identity")
    p_issue.add_argument(
        "--sku", default=PREMIUM_BUNDLE_SKU, help="Product SKU (default: premium-bundle)"
    )
    p_issue.add_argument("--issued", default=None, help="ISO issue date (default: today)")
    p_issue.add_argument(
        "--template",
        default=None,
        help="Template id for premium-single licenses (for example: case-study)",
    )
    p_issue.add_argument(
        "--expires", default=None, help="ISO expiration date for subscription grants"
    )
    p_issue.set_defaults(func=_cmd_issue)

    p_verify = sub.add_parser("verify", help="Verify a license key")
    p_verify.add_argument("--key", required=True, help="License key to verify")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
