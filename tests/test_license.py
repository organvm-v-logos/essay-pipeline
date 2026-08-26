"""Tests for the HMAC license key gate."""

import pytest

from src.license import (
    DEFAULT_SECRET,
    License,
    LicenseError,
    is_valid,
    issue_license,
    verify_license,
)

SECRET = b"unit-test-secret"


class TestRoundTrip:
    def test_issue_then_verify_recovers_payload(self):
        key = issue_license("buyer@example.com", sku="premium-bundle", issued="2026-06-19", secret=SECRET)
        lic = verify_license(key, secret=SECRET)
        assert lic == License(sku="premium-bundle", email="buyer@example.com", issued="2026-06-19")
        assert lic.covers_premium() is True
        assert lic.covers_template("case-study") is True

    def test_single_template_license_covers_only_that_template(self):
        key = issue_license(
            "buyer@example.com",
            sku="premium-single",
            issued="2026-06-19",
            template_id="case-study",
            secret=SECRET,
        )
        lic = verify_license(key, secret=SECRET)
        assert lic == License(
            sku="premium-single",
            email="buyer@example.com",
            issued="2026-06-19",
            template_id="case-study",
        )
        assert lic.covers_premium() is True
        assert lic.covers_template("case-study") is True
        assert lic.covers_template("technical-deep-dive") is False

    def test_default_secret_roundtrips_without_config(self):
        key = issue_license("buyer@example.com")
        lic = verify_license(key)
        assert lic.email == "buyer@example.com"

    def test_issued_defaults_to_a_date(self):
        key = issue_license("a@b.co", secret=SECRET)
        lic = verify_license(key, secret=SECRET)
        # ISO date shape YYYY-MM-DD
        assert len(lic.issued) == 10 and lic.issued[4] == "-"

    def test_key_has_expected_prefix(self):
        key = issue_license("a@b.co", secret=SECRET)
        assert key.startswith("EPK1.")


class TestRejection:
    def test_wrong_secret_fails(self):
        key = issue_license("a@b.co", secret=SECRET)
        with pytest.raises(LicenseError, match="signature mismatch"):
            verify_license(key, secret=b"different-secret")

    def test_tampered_payload_fails(self):
        key = issue_license("a@b.co", sku="premium-bundle", secret=SECRET)
        prefix, payload, sig = key.split(".")
        # Re-sign nothing; just corrupt the payload segment.
        tampered = ".".join([prefix, payload[:-2] + "AA", sig])
        with pytest.raises(LicenseError):
            verify_license(tampered, secret=SECRET)

    def test_truncated_key_fails(self):
        with pytest.raises(LicenseError, match="format"):
            verify_license("EPK1.onlyonesegment", secret=SECRET)

    def test_wrong_prefix_fails(self):
        key = issue_license("a@b.co", secret=SECRET)
        bad = "XXXX" + key[4:]
        with pytest.raises(LicenseError, match="format"):
            verify_license(bad, secret=SECRET)

    def test_garbage_fails(self):
        with pytest.raises(LicenseError):
            verify_license("not-a-license-key", secret=SECRET)

    def test_non_string_fails(self):
        with pytest.raises(LicenseError):
            verify_license(None, secret=SECRET)  # type: ignore[arg-type]

    def test_field_separator_in_email_rejected(self):
        with pytest.raises(LicenseError):
            issue_license("a|b@example.com", secret=SECRET)

    def test_field_separator_in_template_id_rejected(self):
        with pytest.raises(LicenseError):
            issue_license(
                "buyer@example.com",
                sku="premium-single",
                template_id="case|study",
                secret=SECRET,
            )

    def test_single_template_license_requires_template_id(self):
        with pytest.raises(LicenseError, match="template id"):
            issue_license("buyer@example.com", sku="premium-single", secret=SECRET)

    def test_template_id_is_only_for_single_template_licenses(self):
        with pytest.raises(LicenseError, match="premium-single"):
            issue_license(
                "buyer@example.com",
                sku="premium-bundle",
                template_id="case-study",
                secret=SECRET,
            )


class TestIsValid:
    def test_valid_key_true(self):
        key = issue_license("a@b.co", secret=SECRET)
        assert is_valid(key, secret=SECRET) is True

    def test_invalid_key_false(self):
        assert is_valid("nonsense", secret=SECRET) is False

    def test_none_false(self):
        assert is_valid(None) is False

    def test_wrong_secret_false(self):
        key = issue_license("a@b.co", secret=SECRET)
        assert is_valid(key, secret=b"nope") is False


class TestUnknownSku:
    def test_unknown_sku_does_not_cover_premium(self):
        key = issue_license("a@b.co", sku="mystery", secret=SECRET)
        lic = verify_license(key, secret=SECRET)
        assert lic.covers_premium() is False


def test_default_secret_is_documented_demo_value():
    # Guards against accidentally shipping a different baked-in default.
    assert DEFAULT_SECRET == b"organvm-essay-pipeline-demo-secret-v1"
