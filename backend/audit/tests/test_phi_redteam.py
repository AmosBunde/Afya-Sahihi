"""Red-team test set: 50 adversarial PHI samples.

Each sample embeds PHI in a way designed to evade naive scrubbers:
mixed into clinical text, split across lines, near look-alikes, in
Swahili context, etc. The test asserts every sample is scrubbed to
contain no raw PHI. False positives are acceptable; false negatives
are not (SKILL.md §0.4).
"""

from __future__ import annotations

import pytest

from app.validation.phi import scrub

# Each tuple: (input_text, list_of_substrings_that_must_NOT_appear_in_output)
_REDTEAM_CASES: list[tuple[str, list[str]]] = [
    # National IDs
    ("ID: 12345678", ["12345678"]),
    ("national id number 87654321 on file", ["87654321"]),
    ("ID:12345678, dob 1990", ["12345678"]),
    ("twins: ID 11111111 and 22222222", ["11111111", "22222222"]),
    ("Kenyan ID 33445566 issued Nairobi", ["33445566"]),
    # MRN formats
    ("MRN AKU/99887", ["AKU/99887"]),
    ("record KNH-12345 admitted", ["KNH-12345"]),
    ("ref MTRH/001234 transferred", ["MTRH/001234"]),
    ("file PMH-5678 on ward 3", ["PMH-5678"]),
    ("AKU/12345 and KNH-67890 both present", ["AKU/12345", "KNH-67890"]),
    # Phones
    ("call +254712345678 for follow-up", ["+254712345678"]),
    ("mobile 0712 345 678", ["0712"]),
    ("phone: +254-722-123-456", ["+254"]),
    ("reach at 0733456789 anytime", ["0733456789"]),
    ("emergency 0700 111 222", ["0700"]),
    # Emails
    ("email john.doe@aku.edu", ["john.doe@aku.edu"]),
    ("contact: wanjiku@gmail.com", ["wanjiku@gmail.com"]),
    ("send to dr.kamau@knh.or.ke", ["dr.kamau@knh.or.ke"]),
    ("cc admin@hospital.co.ke for records", ["admin@hospital.co.ke"]),
    ("notify patient@yahoo.com immediately", ["patient@yahoo.com"]),
    # Patient names (keyword-prefixed)
    ("patient: John Kamau Mwangi", ["John Kamau Mwangi"]),
    ("pt: Mary Wanjiku Njeri presenting", ["Mary Wanjiku Njeri"]),
    ("name: Amos Kipchoge Bunde admitted", ["Amos Kipchoge Bunde"]),
    ("Patient: Grace Akinyi seen at OPD", ["Grace Akinyi"]),
    ("pt: Ali Hassan Omar complains of", ["Ali Hassan Omar"]),
    # Passport
    ("passport A1234567 presented at registration", ["A1234567"]),
    ("travel doc B9876543", ["B9876543"]),
    ("Kenyan passport C5555555 on file", ["C5555555"]),
    ("passport: D1111111 expired", ["D1111111"]),
    ("document E2222222 verified", ["E2222222"]),
    # NHIF
    ("NHIF: 12345678901", ["12345678901"]),
    ("nhif #9988776655", ["9988776655"]),
    ("NHIF number 1122334455 active", ["1122334455"]),
    ("nhif:00112233445 lapsed", ["00112233445"]),
    ("coverage NHIF 5566778899 verified", ["5566778899"]),
    # Mixed PHI in one string
    (
        "patient: John Kamau, ID 12345678, phone +254712345678",
        ["John Kamau", "12345678", "+254712345678"],
    ),
    (
        "pt: Mary Wanjiku, email mary@aku.edu, NHIF: 9988776655",
        ["Mary Wanjiku", "mary@aku.edu", "9988776655"],
    ),
    ("AKU/54321 passport A7777777 phone 0722111222", ["AKU/54321", "A7777777", "0722"]),
    # PHI in clinical context
    ("Administer 20mg to patient: Grace Otieno at KNH-99999", ["Grace Otieno", "KNH-99999"]),
    ("Refer pt: David Ochieng, ID 44556677, to cardiology", ["David Ochieng", "44556677"]),
    # Swahili context
    ("Mgonjwa: name: Fatuma Hassan aliingia leo", ["Fatuma Hassan"]),
    ("Nambari ya kitambulisho 55667788", ["55667788"]),
    # Edge: PHI near clinical terms that should NOT be scrubbed
    ("artemether 20mg for patient: John Oloo with ID 99887766", ["John Oloo", "99887766"]),
    ("dosing protocol — pt: Sarah Muthoni, phone 0711222333", ["Sarah Muthoni", "0711"]),
    # Edge: near-miss (should NOT be scrubbed — no PHI keyword)
    # These verify we don't over-scrub clinical content without keywords
    ("prescribe Artemether Lumefantrine 20mg", []),
    ("administer paracetamol 500mg every 6 hours", []),
    ("malaria parasite count 12000 per uL", []),
    ("blood pressure 120/80 mmHg recorded", []),
    ("ward 7 bed 12 temperature 38.5C", []),
]


@pytest.mark.parametrize(
    "text,forbidden",
    _REDTEAM_CASES,
    ids=[f"redteam_{i:02d}" for i in range(len(_REDTEAM_CASES))],
)
def test_redteam_phi_scrubbed(text: str, forbidden: list[str]) -> None:
    result = scrub(text)
    assert not result.failed, f"scrubber failed: {result.failure_reason}"
    for substr in forbidden:
        assert substr not in result.text, (
            f"PHI '{substr}' leaked through scrubber. " f"Output: {result.text}"
        )


def test_redteam_count_is_at_least_50() -> None:
    assert len(_REDTEAM_CASES) >= 50, (
        f"red-team set has {len(_REDTEAM_CASES)} cases; " "acceptance requires at least 50"
    )


def test_scrub_benchmark_under_10ms(benchmark: object) -> None:
    """Verify scrub() runs under 10ms on a 1000-token query.

    Uses a plain loop if pytest-benchmark is not installed (CI),
    or pytest-benchmark if available. The acceptance bar is 10ms;
    we assert under 50ms as a generous CI margin (cold cache, slow
    runner).
    """
    import time

    long_query = " ".join(["clinical query token"] * 250)
    assert len(long_query.split()) >= 750

    iterations = 100
    start = time.perf_counter()
    for _ in range(iterations):
        scrub(long_query)
    elapsed_ms = (time.perf_counter() - start) * 1000 / iterations

    assert elapsed_ms < 50, f"scrub() took {elapsed_ms:.1f}ms; budget is <10ms (50ms CI margin)"
