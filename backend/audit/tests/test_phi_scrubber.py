"""PHI scrubber regex tests.

Pure-Python, no fixtures. Exercises every pattern class on both green
(should redact) and edge (should not over-redact on innocent text) paths.
"""

from __future__ import annotations

from app.validation.phi import REPLACEMENT, scrub

# ---- National ID (8-digit Kenyan) ----


def test_national_id_redacted() -> None:
    result = scrub("ID number 12345678 on file")
    assert "12345678" not in result.text
    assert REPLACEMENT in result.text
    assert "national_id" in result.redacted_types


def test_national_id_not_overzealous_on_short_numbers() -> None:
    result = scrub("ward 42 bed 7")
    assert result.n_redactions == 0


# ---- MRN / hospital number ----


def test_mrn_aku_format_redacted() -> None:
    result = scrub("MRN AKU/12345 admitted")
    assert "AKU/12345" not in result.text
    assert "mrn" in result.redacted_types


def test_mrn_knh_format_redacted() -> None:
    result = scrub("Record KNH-67890")
    assert "KNH-67890" not in result.text


def test_mrn_not_triggered_on_adr_paths() -> None:
    result = scrub("see docs/adr/0003-explicit-state-machine.md")
    assert result.n_redactions == 0


# ---- Phone number (Kenyan mobile) ----


def test_phone_plus254_redacted() -> None:
    result = scrub("call +254712345678")
    assert "+254712345678" not in result.text
    assert "phone" in result.redacted_types


def test_phone_07xx_redacted() -> None:
    result = scrub("number 0712 345 678 available")
    assert "0712" not in result.text


def test_phone_not_triggered_on_port_numbers() -> None:
    result = scrub("postgres on port 5432")
    assert result.n_redactions == 0


# ---- Email ----


def test_email_redacted() -> None:
    result = scrub("contact jane.doe@aku.edu for follow-up")
    assert "jane.doe@aku.edu" not in result.text
    assert "email" in result.redacted_types


# ---- Patient name heuristic ----


def test_patient_name_after_keyword_redacted() -> None:
    result = scrub("patient: John Kamau Mwangi presented with fever")
    assert "John Kamau Mwangi" not in result.text
    assert "patient_name" in result.redacted_types


def test_patient_name_pt_prefix_redacted() -> None:
    result = scrub("pt: Mary Wanjiku seen at OPD")
    assert "Mary Wanjiku" not in result.text


def test_patient_name_not_triggered_on_drug_names() -> None:
    result = scrub("prescribe Artemether Lumefantrine for malaria")
    assert result.n_redactions == 0


# ---- Multiple patterns in one pass ----


def test_multiple_phi_types_scrubbed() -> None:
    text = "patient: John Kamau, ID 12345678, phone +254712345678"
    result = scrub(text)
    assert "John Kamau" not in result.text
    assert "12345678" not in result.text
    assert "+254712345678" not in result.text
    assert result.n_redactions >= 3


# ---- Fail-closed ----


def test_scrub_returns_original_text_unchanged_when_no_phi() -> None:
    text = "Administer 20mg artemether per dose"
    result = scrub(text)
    assert result.text == text
    assert result.n_redactions == 0
    assert not result.failed
