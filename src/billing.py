"""Stripe Checkout bridge for essay-pipeline premium access.

The template store remains the enforcement point: free templates are always
readable, and premium templates require a license key. This module connects a
Stripe sale to that existing gate by creating Checkout sessions and converting
verified Stripe webhook events into signed essay-pipeline license keys.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import httpx

from .license import KNOWN_SKUS, issue_license

STRIPE_CHECKOUT_SESSIONS_URL = "https://api.stripe.com/v1/checkout/sessions"
STRIPE_PROVIDER = "stripe"
DEFAULT_CHECKOUT_MODE = "payment"
SUPPORTED_CHECKOUT_MODES = {"payment", "subscription"}
PAID_CHECKOUT_STATUSES = {"paid", "no_payment_required"}
ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}
SUBSCRIPTION_GRANT_EVENTS = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.resumed",
}


class BillingError(Exception):
    """Raised when checkout creation or webhook processing cannot continue."""


@dataclass(frozen=True)
class CheckoutSession:
    """A hosted Stripe Checkout session for a premium SKU."""

    provider: str
    id: str
    url: str
    sku: str
    mode: str
    price_id: str


@dataclass(frozen=True)
class LicenseGrant:
    """A license key issued from a paid provider event."""

    provider: str
    event_id: str
    event_type: str
    sku: str
    email: str
    license_key: str
    subscription_id: str | None = None
    expires: str | None = None


def stripe_price_env_var(sku: str) -> str:
    """Return the env var name used to configure a Stripe Price for a SKU."""
    normalized = "".join(ch if ch.isalnum() else "_" for ch in sku.upper())
    return f"STRIPE_PRICE_{normalized}"


def create_stripe_checkout_session(
    *,
    sku: str,
    success_url: str,
    cancel_url: str,
    customer_email: str | None = None,
    mode: str = DEFAULT_CHECKOUT_MODE,
    api_key: str | None = None,
    price_id: str | None = None,
    metadata: Mapping[str, str | None] | None = None,
    env: Mapping[str, str] | None = None,
    client: httpx.Client | None = None,
) -> CheckoutSession:
    """Create a Stripe Checkout session for a known premium SKU.

    The function uses raw HTTPS instead of the Stripe SDK to keep the package's
    dependency surface small. It expects ``STRIPE_SECRET_KEY`` and
    ``STRIPE_PRICE_<SKU>`` unless explicit values are passed.
    """
    _require_known_sku(sku)
    if mode not in SUPPORTED_CHECKOUT_MODES:
        raise BillingError(
            f"Unsupported Stripe Checkout mode '{mode}'. "
            f"Use one of {sorted(SUPPORTED_CHECKOUT_MODES)}."
        )
    if not success_url or not cancel_url:
        raise BillingError("success_url and cancel_url are required for Stripe Checkout")

    resolved_env = env if env is not None else os.environ
    resolved_api_key = api_key or resolved_env.get("STRIPE_SECRET_KEY")
    if not resolved_api_key:
        raise BillingError("Missing STRIPE_SECRET_KEY for Stripe Checkout")

    price_var = stripe_price_env_var(sku)
    resolved_price_id = price_id or resolved_env.get(price_var)
    if not resolved_price_id:
        raise BillingError(f"Missing {price_var} for SKU '{sku}'")

    session_metadata: dict[str, str] = {"sku": sku, "product": "essay-pipeline"}
    if customer_email:
        session_metadata["customer_email"] = customer_email
    if metadata:
        session_metadata.update(
            {key: value for key, value in metadata.items() if value is not None}
        )

    data = {
        "mode": mode,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][price]": resolved_price_id,
        "line_items[0][quantity]": "1",
        "client_reference_id": sku,
        "allow_promotion_codes": "true",
    }
    if customer_email:
        data["customer_email"] = customer_email
    for key, value in session_metadata.items():
        data[f"metadata[{key}]"] = value
        if mode == "subscription":
            data[f"subscription_data[metadata][{key}]"] = value
        else:
            data[f"payment_intent_data[metadata][{key}]"] = value

    active_client = client or httpx.Client(timeout=15.0)
    close_client = client is None
    try:
        response = active_client.post(
            STRIPE_CHECKOUT_SESSIONS_URL,
            data=data,
            headers={"Authorization": f"Bearer {resolved_api_key}"},
        )
    finally:
        if close_client:
            active_client.close()

    if response.status_code >= 400:
        raise BillingError(_stripe_error_message(response))

    try:
        body = response.json()
    except ValueError as exc:
        raise BillingError("Stripe returned a non-JSON Checkout response") from exc

    session_id = body.get("id")
    url = body.get("url")
    if not isinstance(session_id, str) or not isinstance(url, str):
        raise BillingError("Stripe Checkout response did not include id and url")

    return CheckoutSession(
        provider=STRIPE_PROVIDER,
        id=session_id,
        url=url,
        sku=sku,
        mode=mode,
        price_id=resolved_price_id,
    )


def parse_stripe_event(
    payload: bytes | str,
    signature_header: str,
    webhook_secret: str,
    *,
    now: int | None = None,
    tolerance: int = 300,
) -> dict[str, Any]:
    """Verify a Stripe webhook signature and return the event payload."""
    if not signature_header:
        raise BillingError("Missing Stripe-Signature header")
    if not webhook_secret:
        raise BillingError("Missing STRIPE_WEBHOOK_SECRET")

    payload_bytes = payload.encode("utf-8") if isinstance(payload, str) else payload
    timestamp, signatures = _parse_stripe_signature_header(signature_header)
    current_time = int(time.time()) if now is None else int(now)
    if tolerance >= 0 and abs(current_time - timestamp) > tolerance:
        raise BillingError("Stripe webhook timestamp is outside the allowed tolerance")

    signed_payload = f"{timestamp}.".encode("ascii") + payload_bytes
    expected = hmac.new(
        webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise BillingError("Stripe webhook signature mismatch")

    try:
        event = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BillingError("Stripe webhook payload is not valid JSON") from exc
    if not isinstance(event, dict):
        raise BillingError("Stripe webhook payload must be a JSON object")
    return event


def license_grant_from_stripe_event(
    event: Mapping[str, Any],
    *,
    secret: bytes | str | None = None,
    issued: str | None = None,
) -> LicenseGrant | None:
    """Issue a license key from a paid Stripe event, if the event grants access."""
    event_type = event.get("type")
    if not isinstance(event_type, str):
        raise BillingError("Stripe event is missing a type")

    if event_type == "checkout.session.completed":
        obj = _event_object(event)
        return _grant_from_checkout_session(event, obj, secret=secret, issued=issued)
    if event_type in SUBSCRIPTION_GRANT_EVENTS:
        obj = _event_object(event)
        return _grant_from_subscription(event, obj, secret=secret, issued=issued)
    return None


def process_stripe_webhook(
    payload: bytes | str,
    signature_header: str,
    webhook_secret: str,
    *,
    license_secret: bytes | str | None = None,
    now: int | None = None,
    tolerance: int = 300,
) -> LicenseGrant | None:
    """Verify a Stripe webhook and issue a license grant when applicable."""
    event = parse_stripe_event(
        payload,
        signature_header,
        webhook_secret,
        now=now,
        tolerance=tolerance,
    )
    return license_grant_from_stripe_event(event, secret=license_secret)


def _grant_from_checkout_session(
    event: Mapping[str, Any],
    obj: Mapping[str, Any],
    *,
    secret: bytes | str | None,
    issued: str | None,
) -> LicenseGrant | None:
    # Subscription sessions are granted from customer.subscription events where
    # Stripe includes the current billing-period end date.
    if obj.get("mode") == "subscription":
        return None
    if obj.get("status") not in {None, "complete"}:
        return None
    if obj.get("payment_status") not in PAID_CHECKOUT_STATUSES:
        return None

    sku = _extract_sku(obj)
    if not sku:
        raise BillingError("Paid Stripe Checkout session is missing metadata.sku")
    email = _extract_email(obj)
    if not email:
        raise BillingError("Paid Stripe Checkout session is missing buyer email")

    return _issue_license_grant(
        event=event,
        sku=sku,
        email=email,
        secret=secret,
        issued=issued,
    )


def _grant_from_subscription(
    event: Mapping[str, Any],
    obj: Mapping[str, Any],
    *,
    secret: bytes | str | None,
    issued: str | None,
) -> LicenseGrant | None:
    if obj.get("status") not in ACTIVE_SUBSCRIPTION_STATUSES:
        return None

    sku = _extract_sku(obj) or "premium-subscription"
    email = _extract_email(obj)
    if not email:
        raise BillingError(
            "Active Stripe subscription is missing buyer email. "
            "Pass --email when creating subscription checkout sessions so it is "
            "copied into subscription metadata."
        )
    expires = _stripe_timestamp_to_date(obj.get("current_period_end"))
    subscription_id = obj.get("id") if isinstance(obj.get("id"), str) else None

    return _issue_license_grant(
        event=event,
        sku=sku,
        email=email,
        secret=secret,
        issued=issued,
        subscription_id=subscription_id,
        expires=expires,
    )


def _issue_license_grant(
    *,
    event: Mapping[str, Any],
    sku: str,
    email: str,
    secret: bytes | str | None,
    issued: str | None,
    subscription_id: str | None = None,
    expires: str | None = None,
) -> LicenseGrant:
    _require_known_sku(sku)
    event_id = event.get("id") if isinstance(event.get("id"), str) else ""
    event_type = event.get("type") if isinstance(event.get("type"), str) else ""
    key = issue_license(
        email=email,
        sku=sku,
        issued=issued,
        expires=expires,
        secret=secret,
    )
    return LicenseGrant(
        provider=STRIPE_PROVIDER,
        event_id=event_id,
        event_type=event_type,
        sku=sku,
        email=email,
        license_key=key,
        subscription_id=subscription_id,
        expires=expires,
    )


def _require_known_sku(sku: str) -> None:
    if sku not in KNOWN_SKUS:
        raise BillingError(f"Unknown SKU '{sku}'. Known SKUs: {sorted(KNOWN_SKUS)}")


def _parse_stripe_signature_header(header: str) -> tuple[int, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise BillingError("Stripe-Signature timestamp is invalid") from exc
        elif key == "v1" and value:
            signatures.append(value)

    if timestamp is None:
        raise BillingError("Stripe-Signature header is missing t")
    if not signatures:
        raise BillingError("Stripe-Signature header is missing v1")
    return timestamp, signatures


def _event_object(event: Mapping[str, Any]) -> Mapping[str, Any]:
    data = event.get("data")
    if not isinstance(data, Mapping):
        raise BillingError("Stripe event is missing data")
    obj = data.get("object")
    if not isinstance(obj, Mapping):
        raise BillingError("Stripe event is missing data.object")
    return obj


def _extract_sku(obj: Mapping[str, Any]) -> str | None:
    metadata = _metadata(obj)
    for key in ("sku", "product_sku"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value

    ref = obj.get("client_reference_id")
    if isinstance(ref, str) and ref in KNOWN_SKUS:
        return ref

    items = obj.get("items")
    if isinstance(items, Mapping):
        data = items.get("data")
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, Mapping):
                    continue
                price = item.get("price")
                if not isinstance(price, Mapping):
                    continue
                price_metadata = _metadata(price)
                value = price_metadata.get("sku")
                if isinstance(value, str) and value:
                    return value
                lookup_key = price.get("lookup_key")
                if isinstance(lookup_key, str) and lookup_key in KNOWN_SKUS:
                    return lookup_key
    return None


def _extract_email(obj: Mapping[str, Any]) -> str | None:
    customer_details = obj.get("customer_details")
    if isinstance(customer_details, Mapping):
        email = customer_details.get("email")
        if isinstance(email, str) and email:
            return email

    for key in ("customer_email", "receipt_email", "email"):
        email = obj.get(key)
        if isinstance(email, str) and email:
            return email

    metadata = _metadata(obj)
    for key in ("customer_email", "buyer_email", "email"):
        email = metadata.get(key)
        if isinstance(email, str) and email:
            return email
    return None


def _metadata(obj: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = obj.get("metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _stripe_timestamp_to_date(value: Any) -> str:
    if not isinstance(value, int):
        raise BillingError("Active Stripe subscription is missing current_period_end")
    return datetime.fromtimestamp(value, timezone.utc).date().isoformat()


def _stripe_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"Stripe Checkout failed with HTTP {response.status_code}: {response.text}"

    if isinstance(body, Mapping):
        error = body.get("error")
        if isinstance(error, Mapping) and isinstance(error.get("message"), str):
            return f"Stripe Checkout failed: {error['message']}"
    return f"Stripe Checkout failed with HTTP {response.status_code}"


def _read_payload(path: str | None) -> bytes:
    if path:
        return Path(path).read_bytes()
    return sys.stdin.buffer.read()


def _cmd_checkout(args: argparse.Namespace) -> int:
    try:
        session = create_stripe_checkout_session(
            sku=args.sku,
            success_url=args.success_url,
            cancel_url=args.cancel_url,
            customer_email=args.email,
            mode=args.mode,
            api_key=args.api_key,
            price_id=args.price_id,
        )
    except BillingError as exc:
        print(f"ERROR - {exc}", file=sys.stderr)
        return 1

    print(session.url)
    print(f"session: {session.id}")
    print(f"sku: {session.sku}")
    print(f"mode: {session.mode}")
    return 0


def _cmd_stripe_webhook(args: argparse.Namespace) -> int:
    signature = args.signature or os.environ.get("STRIPE_SIGNATURE")
    webhook_secret = args.webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not signature:
        print("ERROR - missing --signature or STRIPE_SIGNATURE", file=sys.stderr)
        return 1
    if not webhook_secret:
        print("ERROR - missing --webhook-secret or STRIPE_WEBHOOK_SECRET", file=sys.stderr)
        return 1

    try:
        grant = process_stripe_webhook(
            _read_payload(args.payload_file),
            signature,
            webhook_secret,
            license_secret=args.license_secret,
        )
    except BillingError as exc:
        print(f"ERROR - {exc}", file=sys.stderr)
        return 1

    if grant is None:
        print("NO_GRANT")
        return 0

    print("LICENSE_ISSUED")
    print(f"  provider: {grant.provider}")
    print(f"  event:    {grant.event_id}")
    print(f"  sku:      {grant.sku}")
    print(f"  email:    {grant.email}")
    if grant.expires:
        print(f"  expires:  {grant.expires}")
    print(f"  key:      {grant.license_key}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Stripe billing for essay-pipeline premium access")
    sub = parser.add_subparsers(dest="command", required=True)

    p_checkout = sub.add_parser("checkout", help="Create a Stripe Checkout session")
    p_checkout.add_argument("--sku", default="premium-bundle", help="Premium SKU to sell")
    p_checkout.add_argument(
        "--mode",
        default=DEFAULT_CHECKOUT_MODE,
        choices=sorted(SUPPORTED_CHECKOUT_MODES),
        help="Stripe Checkout mode",
    )
    p_checkout.add_argument("--success-url", required=True, help="Redirect URL after payment")
    p_checkout.add_argument("--cancel-url", required=True, help="Redirect URL after cancellation")
    p_checkout.add_argument("--email", default=None, help="Pre-fill buyer email")
    p_checkout.add_argument("--api-key", default=None, help="Override STRIPE_SECRET_KEY")
    p_checkout.add_argument("--price-id", default=None, help="Override STRIPE_PRICE_<SKU>")
    p_checkout.set_defaults(func=_cmd_checkout)

    p_webhook = sub.add_parser(
        "stripe-webhook",
        help="Verify a Stripe webhook payload and print any issued license key",
    )
    p_webhook.add_argument(
        "--payload-file", default=None, help="JSON payload file (default: stdin)"
    )
    p_webhook.add_argument("--signature", default=None, help="Stripe-Signature header")
    p_webhook.add_argument("--webhook-secret", default=None, help="Override STRIPE_WEBHOOK_SECRET")
    p_webhook.add_argument(
        "--license-secret",
        default=None,
        help="Override ESSAY_PIPELINE_LICENSE_SECRET",
    )
    p_webhook.set_defaults(func=_cmd_stripe_webhook)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
