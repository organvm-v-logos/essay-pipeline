"""Tests for the HMAC offline license key system."""

from datetime import date
import pytest

from src.license import (
    KNOWN_SKUS,
    PREMIUM_BUNDLE_SKU,
    PREMIUM_SINGLE_SKU,
    PREMIUM_SUBSCRIPTION_SKU,
    License,
    LicenseError,
    is_valid,
    issue_license,
    verify_license,
)

SECRET = b"unit-test-secret-value-12345"  # allow-secret


class TestRoundtrip:
    def test_issue_then_verify_recovers_payload(self):
        key = issue_license("buyer@example.com", sku="premium-bundle", issued="2026-06-19", secret=SECRET)  # allow-secret
        lic = verify_license(key, secret=SECRET)  # allow-secret
        assert lic == License(sku="premium-bundle", email="buyer@example.com", issued="2026-06-19")
        assert lic.covers_premium() is True
        assert lic.covers_template("case-study") is True

    def test_single_template_license_covers_only_that_template(self):
        key = issue_license(  # allow-secret
            "buyer@example.com",
            sku="premium-single",
            issued="2026-06-19",
            template_id="case-study",
            secret=SECRET,  # allow-secret
        )
        lic = verify_license(key, secret=SECRET)  # allow-secret
        assert lic == License(
            sku="premium-single",
            email="buyer@example.com",
            issued="2026-06-19",
            template_id="case-study",
        )
        assert lic.covers_premium() is True
        assert lic.covers_template("case-study") is True
        assert lic.covers_template("technical-deep-dive") is False

    def test_subscription_license_with_expiration(self):
        key = issue_license(  # allow-secret
            "buyer@example.com",
            sku="premium-subscription",
            issued="2026-06-19",
            expires="2099-01-01",
            secret=SECRET,  # allow-secret
        )
        lic = verify_license(key, secret=SECRET)  # allow-secret
        assert lic.sku == "premium-subscription"
        assert lic.expires == "2099-01-01"
        assert lic.covers_premium() is True

    def test_expired_subscription_license(self):
        key = issue_license(  # allow-secret
            "buyer@example.com",
            sku="premium-subscription",
            issued="2026-06-19",
            expires="2000-01-01",
            secret=SECRET,  # allow-secret
        )
        lic = verify_license(key, secret=SECRET)  # allow-secret
        assert lic.covers_premium() is False

    def test_default_secret_roundtrips_without_config(self):  # allow-secret
        key = issue_license("buyer@example.com")  # allow-secret
        lic = verify_license(key)
        assert lic.email == "buyer@example.com"
        assert lic.sku == "premium-bundle"
        assert lic.issued == date.today().isoformat()

    def test_tampered_payload_rejected(self):
        key = issue_license("buyer@example.com", secret=SECRET)  # allow-secret
        prefix, payload, sig = key.split(".")
        tampered_key = f"{prefix}.AAAA.{sig}"  # allow-secret
        with pytest.raises(LicenseError, match="mismatch|corrupt"):
            verify_license(tampered_key, secret=SECRET)  # allow-secret

    def test_wrong_secret_fails_verification(self):  # allow-secret
        key = issue_license("buyer@example.com", secret=SECRET)  # allow-secret
        with pytest.raises(LicenseError, match="mismatch"):
            verify_license(key, secret=b"different-secret")  # allow-secret

    def test_malformed_key_structure_rejected(self):
        for bad in ["", "foo", "EPK1.abc", "EPK1.a.b.c", "OTHER.a.b"]:
            with pytest.raises(LicenseError):
                verify_license(bad, secret=SECRET)  # allow-secret

    def test_field_separator_in_email_rejected(self):
        with pytest.raises(LicenseError):
            issue_license("a|b@example.com", secret=SECRET)  # allow-secret

    def test_field_separator_in_template_id_rejected(self):
        with pytest.raises(LicenseError):
            issue_license(
                "buyer@example.com",
                sku="premium-single",
                template_id="case|study",
                secret=SECRET,  # allow-secret
            )

    def test_single_template_license_requires_template_id(self):
        with pytest.raises(LicenseError, match="template id"):
            issue_license("buyer@example.com", sku="premium-single", secret=SECRET)  # allow-secret

    def test_template_id_is_only_for_single_template_licenses(self):
        with pytest.raises(LicenseError, match="premium-single"):
            issue_license(
                "buyer@example.com",
                sku="premium-bundle",
                template_id="case-study",
                secret=SECRET,  # allow-secret
            )


class TestIsValid:
    def test_valid_key_true(self):
        key = issue_license("a@b.com", secret=SECRET)  # allow-secret
        assert is_valid(key, secret=SECRET) is True  # allow-secret

    def test_invalid_key_false(self):
        assert is_valid("EPK1.bad.sig", secret=SECRET) is False  # allow-secret
        assert is_valid(None, secret=SECRET) is False  # allow-secret
        assert is_valid("", secret=SECRET) is False  # allow-secret
