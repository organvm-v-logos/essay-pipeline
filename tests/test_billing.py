"""Tests for the Stripe billing bridge."""

import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from src.billing import (
    BillingError,
    create_stripe_checkout_session,
    license_grant_from_stripe_event,
    parse_stripe_event,
    process_stripe_webhook,
    stripe_price_env_var,
)
from src.license import verify_license

SECRET = b"unit-test-secret"  # allow-secret
WEBHOOK_SECRET = "whsec_test"  # allow-secret


def _payload(event):
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def _signature(payload: bytes, secret: str = WEBHOOK_SECRET, timestamp: int = 12345):  # allow-secret
    digest = hmac.new(
        secret.encode("utf-8"),  # allow-secret
        f"{timestamp}.".encode("ascii") + payload,
        hashlib.sha256,
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_stripe_price_env_var_normalizes_sku():
    assert stripe_price_env_var("premium-bundle") == "STRIPE_PRICE_PREMIUM_BUNDLE"


def test_create_checkout_session_posts_stripe_form():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["form"] = parse_qs(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"id": "cs_test_123", "url": "https://checkout.stripe.com/c/pay"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    session = create_stripe_checkout_session(
        sku="premium-bundle",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        customer_email="buyer@example.com",
        env={
            "STRIPE_SECRET_KEY": "sk_test_123",  # allow-secret
            "STRIPE_PRICE_PREMIUM_BUNDLE": "price_bundle",
        },
        client=client,
    )

    assert session.id == "cs_test_123"
    assert session.url == "https://checkout.stripe.com/c/pay"
    assert captured["url"] == "https://api.stripe.com/v1/checkout/sessions"
    assert captured["authorization"] == "Bearer sk_test_123"
    assert captured["form"]["mode"] == ["payment"]
    assert captured["form"]["line_items[0][price]"] == ["price_bundle"]
    assert captured["form"]["customer_email"] == ["buyer@example.com"]
    assert captured["form"]["metadata[sku]"] == ["premium-bundle"]
    assert captured["form"]["payment_intent_data[metadata][sku]"] == ["premium-bundle"]


def test_create_subscription_checkout_copies_metadata_to_subscription():
    captured = {}

    def handler(request):
        captured["form"] = parse_qs(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"id": "cs_test_sub", "url": "https://checkout.stripe.com/c/sub"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    create_stripe_checkout_session(
        sku="premium-subscription",
        mode="subscription",
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
        customer_email="buyer@example.com",
        env={
            "STRIPE_SECRET_KEY": "sk_test_123",  # allow-secret
            "STRIPE_PRICE_PREMIUM_SUBSCRIPTION": "price_sub",
        },
        client=client,
    )

    assert captured["form"]["mode"] == ["subscription"]
    assert captured["form"]["subscription_data[metadata][sku]"] == [
        "premium-subscription"
    ]
    assert captured["form"]["subscription_data[metadata][customer_email]"] == [
        "buyer@example.com"
    ]


def test_create_checkout_requires_secret_and_price():  # allow-secret
    with pytest.raises(BillingError, match="STRIPE_SECRET_KEY"):  # allow-secret
        create_stripe_checkout_session(
            sku="premium-bundle",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            env={},
        )

    with pytest.raises(BillingError, match="STRIPE_PRICE_PREMIUM_BUNDLE"):
        create_stripe_checkout_session(
            sku="premium-bundle",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            env={"STRIPE_SECRET_KEY": "sk_test"},  # allow-secret
        )


def test_parse_stripe_event_accepts_valid_signature():
    event = {"id": "evt_123", "type": "checkout.session.completed"}
    payload = _payload(event)
    parsed = parse_stripe_event(
        payload,
        _signature(payload, timestamp=200),
        WEBHOOK_SECRET,  # allow-secret
        now=200,
    )
    assert parsed == event


def test_parse_stripe_event_rejects_bad_signature():
    event = {"id": "evt_123", "type": "checkout.session.completed"}
    payload = _payload(event)
    with pytest.raises(BillingError, match="signature mismatch"):
        parse_stripe_event(
            payload,
            _signature(payload, secret="wrong", timestamp=200),  # allow-secret
            WEBHOOK_SECRET,  # allow-secret
            now=200,
        )


def test_parse_stripe_event_rejects_stale_timestamp():
    event = {"id": "evt_123", "type": "checkout.session.completed"}
    payload = _payload(event)
    with pytest.raises(BillingError, match="timestamp"):
        parse_stripe_event(
            payload,
            _signature(payload, timestamp=100),
            WEBHOOK_SECRET,  # allow-secret
            now=1000,
            tolerance=300,
        )


def test_paid_checkout_session_issues_license_key():
    event = {
        "id": "evt_checkout",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test",
                "mode": "payment",
                "status": "complete",
                "payment_status": "paid",
                "metadata": {"sku": "premium-bundle"},
                "customer_details": {"email": "buyer@example.com"},
            }
        },
    }

    grant = license_grant_from_stripe_event(event, secret=SECRET, issued="2026-06-20")  # allow-secret

    assert grant is not None
    assert grant.sku == "premium-bundle"
    assert grant.email == "buyer@example.com"
    lic = verify_license(grant.license_key, secret=SECRET)  # allow-secret
    assert lic.email == "buyer@example.com"
    assert lic.covers_premium() is True


def test_unpaid_checkout_session_does_not_issue_license_key():
    event = {
        "id": "evt_checkout",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "payment",
                "status": "complete",
                "payment_status": "unpaid",
                "metadata": {"sku": "premium-bundle"},
                "customer_details": {"email": "buyer@example.com"},
            }
        },
    }

    assert license_grant_from_stripe_event(event, secret=SECRET) is None  # allow-secret


def test_active_subscription_issues_expiring_license_key():
    period_end = int(datetime(2026, 7, 19, tzinfo=timezone.utc).timestamp())
    event = {
        "id": "evt_subscription",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "id": "sub_123",
                "status": "active",
                "current_period_end": period_end,
                "metadata": {
                    "sku": "premium-subscription",
                    "customer_email": "buyer@example.com",
                },
            }
        },
    }

    grant = license_grant_from_stripe_event(event, secret=SECRET, issued="2026-06-20")  # allow-secret

    assert grant is not None
    assert grant.subscription_id == "sub_123"
    assert grant.expires == "2026-07-19"
    lic = verify_license(grant.license_key, secret=SECRET)  # allow-secret
    assert lic.covers_premium(as_of="2026-07-19") is True
    assert lic.covers_premium(as_of="2026-07-20") is False


def test_canceled_subscription_does_not_issue_license_key():
    event = {
        "id": "evt_subscription",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "status": "canceled",
                "current_period_end": 1784419200,
                "metadata": {
                    "sku": "premium-subscription",
                    "customer_email": "buyer@example.com",
                },
            }
        },
    }

    assert license_grant_from_stripe_event(event, secret=SECRET) is None  # allow-secret


def test_process_stripe_webhook_verifies_and_issues_license():
    event = {
        "id": "evt_checkout",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "payment",
                "status": "complete",
                "payment_status": "paid",
                "metadata": {"sku": "premium-bundle"},
                "customer_details": {"email": "buyer@example.com"},
            }
        },
    }
    payload = _payload(event)

    grant = process_stripe_webhook(
        payload,
        _signature(payload, timestamp=300),
        WEBHOOK_SECRET,  # allow-secret
        license_secret=SECRET,  # allow-secret
        now=300,
    )

    assert grant is not None
    assert verify_license(grant.license_key, secret=SECRET).covers_premium() is True  # allow-secret
