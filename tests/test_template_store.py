"""Tests for the licensed template store."""

import pytest

from src.license import issue_license
from src.template_store import (
    LicenseRequired,
    TemplateNotFound,
    _cmd_list,
    get_entry,
    is_unlocked,
    list_templates,
    read_template,
)

SECRET = b"unit-test-secret"  # allow-secret


def _bundle_key():
    return issue_license("buyer@example.com", sku="premium-bundle", secret=SECRET)  # allow-secret


def _single_key(template_id: str):
    return issue_license(
        "buyer@example.com",
        sku="premium-single",
        template_id=template_id,
        secret=SECRET,  # allow-secret
    )


class TestCatalog:
    def test_manifest_lists_templates(self):
        entries = list_templates()
        ids = {e.id for e in entries}
        assert "field-note" in ids
        assert "case-study" in ids
        assert len(entries) >= 6

    def test_free_template_marked_free(self):
        assert get_entry("field-note").tier == "free"
        assert get_entry("field-note").is_premium is False

    def test_premium_template_marked_premium(self):
        assert get_entry("case-study").is_premium is True

    def test_unknown_id_raises(self):
        with pytest.raises(TemplateNotFound):
            get_entry("does-not-exist")

    def test_every_manifest_path_exists_on_disk(self):
        for entry in list_templates():
            key = None if not entry.is_premium else _bundle_key()  # allow-secret
            body = read_template(entry.id, license_key=key, secret=SECRET)  # allow-secret
            assert body.strip(), f"{entry.id} resolved to empty body"


class TestGate:
    def test_free_readable_without_license(self):
        body = read_template("field-note")
        assert "layout: essay" in body

    def test_premium_denied_without_license(self):
        with pytest.raises(LicenseRequired):
            read_template("case-study")

    def test_premium_denied_with_invalid_license(self):
        with pytest.raises(LicenseRequired):
            read_template("case-study", license_key="EPK1.bogus.bogus", secret=SECRET)  # allow-secret

    def test_premium_denied_with_wrong_secret(self):  # allow-secret
        key = issue_license("a@b.co", sku="premium-bundle", secret=b"attacker")  # allow-secret
        with pytest.raises(LicenseRequired):
            read_template("case-study", license_key=key, secret=SECRET)  # allow-secret

    def test_premium_allowed_with_valid_license(self):
        body = read_template("case-study", license_key=_bundle_key(), secret=SECRET)  # allow-secret
        assert "layout: essay" in body

    def test_single_sku_grants_matching_template_access(self):
        key = _single_key("technical-deep-dive")  # allow-secret
        body = read_template("technical-deep-dive", license_key=key, secret=SECRET)  # allow-secret
        assert "layout: essay" in body

    def test_single_sku_denies_unmatched_template_access(self):
        key = _single_key("technical-deep-dive")  # allow-secret
        with pytest.raises(LicenseRequired):
            read_template("case-study", license_key=key, secret=SECRET)  # allow-secret

    def test_active_subscription_license_grants_access(self):
        key = issue_license(  # allow-secret
            "a@b.co",
            sku="premium-subscription",
            expires="2999-01-01",
            secret=SECRET,  # allow-secret
        )
        body = read_template("technical-deep-dive", license_key=key, secret=SECRET)  # allow-secret
        assert "layout: essay" in body

    def test_expired_subscription_license_does_not_unlock(self):
        key = issue_license(  # allow-secret
            "a@b.co",
            sku="premium-subscription",
            expires="2000-01-01",
            secret=SECRET,  # allow-secret
        )
        with pytest.raises(LicenseRequired):
            read_template("case-study", license_key=key, secret=SECRET)  # allow-secret

    def test_unknown_sku_does_not_unlock(self):
        key = issue_license("a@b.co", sku="freebie", secret=SECRET)  # allow-secret
        with pytest.raises(LicenseRequired):
            read_template("case-study", license_key=key, secret=SECRET)  # allow-secret


class TestIsUnlocked:
    def test_free_always_unlocked(self):
        assert is_unlocked(get_entry("field-note")) is True

    def test_premium_locked_without_key(self):
        assert is_unlocked(get_entry("case-study")) is False

    def test_premium_unlocked_with_key(self):
        assert is_unlocked(get_entry("case-study"), license_key=_bundle_key(), secret=SECRET) is True  # allow-secret

    def test_single_key_only_unlocks_matching_entry(self):
        key = _single_key("case-study")  # allow-secret
        assert is_unlocked(get_entry("case-study"), license_key=key, secret=SECRET) is True  # allow-secret
        assert is_unlocked(get_entry("announcement"), license_key=key, secret=SECRET) is False  # allow-secret


class TestListCommand:
    def test_expired_subscription_is_listed_as_locked(self, capsys):
        key = issue_license(  # allow-secret
            "a@b.co",
            sku="premium-subscription",
            expires="2000-01-01",
        )
        assert _cmd_list(type("Args", (), {"license": key})()) == 0
        out = capsys.readouterr().out
        assert "locked" in out
