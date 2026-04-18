"""Tests for the labeling PHI scrubber."""

from __future__ import annotations

from labeling.phi import REPLACEMENT, scrub


def test_scrub_redacts_kenyan_national_id() -> None:
    result = scrub("ID is 12345678 in the records.")
    assert REPLACEMENT in result.scrubbed
    assert "12345678" not in result.scrubbed
    assert "national_id" in result.hits
    assert result.failed is False


def test_scrub_redacts_phone_with_country_code() -> None:
    result = scrub("Call +254 712 345 678")
    assert "712" not in result.scrubbed
    assert "phone" in result.hits


def test_scrub_redacts_local_phone_format() -> None:
    result = scrub("Call 0712 345 678")
    assert "0712" not in result.scrubbed


def test_scrub_redacts_email() -> None:
    result = scrub("Contact: dr.smith@aku.edu for follow-up.")
    assert "dr.smith@aku.edu" not in result.scrubbed
    assert "email" in result.hits


def test_scrub_redacts_mrn() -> None:
    result = scrub("Patient MRN ABC-123456")
    assert "ABC-123456" not in result.scrubbed


def test_scrub_clean_text_unchanged() -> None:
    result = scrub("The guideline recommends aspirin 300mg stat.")
    assert result.scrubbed == "The guideline recommends aspirin 300mg stat."
    assert result.hits == ()
    assert result.failed is False


def test_scrub_non_string_fails_closed() -> None:
    result = scrub(None)  # type: ignore[arg-type]
    assert result.failed is True
    assert result.scrubbed == ""


def test_scrub_empty_string_succeeds() -> None:
    result = scrub("")
    assert result.scrubbed == ""
    assert result.failed is False
    assert result.hits == ()
