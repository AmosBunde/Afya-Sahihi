# Tier 1 golden-set schema

`eval/datasets/tier1_golden.jsonl` is the 500-case Tier 1 evaluation
dataset. Each line is a JSON object representing one clinical case.

## Schema

```json
{
  "id": "t1-malaria-001",
  "query": "What is the first-line treatment for uncomplicated malaria in a 5-year-old?",
  "key_facts": {
    "drug": "artemether-lumefantrine",
    "dose": "20/120 mg per tablet",
    "route": "oral",
    "frequency": "twice daily",
    "duration": "3 days"
  },
  "language": "en",
  "intent": "malaria_treatment",
  "source": "moh-kenya-malaria-guidelines-v7",
  "reviewer": "clinician_panel_2026q1"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | yes | Unique. Prefix by domain: `t1-malaria-001`. |
| `query` | string | yes | The question as a clinician would ask it. Must be PHI-free. |
| `key_facts` | object | yes | Required facts. Missing/empty values excluded from scoring. |
| `language` | string | no | `en`, `sw`, `en-sw`. Default `en`. |
| `intent` | string | yes | Must match the 42-intent taxonomy from issue #17. |
| `source` | string | yes | MoH document ID that the case is grounded in. |
| `reviewer` | string | yes | Provenance — which clinician panel signed off. |

## Curation process

The 500-case dataset is produced by the clinical panel per ADR-0006,
not in code review. This repo ships a 30-case seed demonstrating the
schema and exercising the scorer across the major domains (malaria,
TB, HIV, maternal health, pediatric, dosing, contraindications). The
full 500 is loaded at eval time from MinIO at
`s3://afya-sahihi-corpus/eval/tier1_golden_v1.jsonl` and mounted into
the eval container by the CronJob.

When extending the seed set in this repo:

1. Pick cases from MoH Kenya clinical guidelines (public, not PHI).
2. Phrase the query the way a Kenyan clinician would.
3. Extract 3–5 key facts that are the *clinically essential* bits of
   the answer. Missing a key fact should mean the response is wrong
   in a way that matters for patient care.
4. Never embed PHI. If a case needs a patient age, use a range
   (`5-year-old`, `pregnant woman`, `elderly patient`).
5. Run `pytest eval/tests/test_scorer.py -v` before committing.

## Key-fact scoring rules

- Normalization: case-insensitive, whitespace-collapsed, accent-stripped.
- Substring match: expected value must appear as a substring of the
  normalized response.
- Every listed key-fact is required; partial matches do not pass.
- Empty/missing values in `key_facts` are excluded from the required
  set — use this for cases where (e.g.) duration is not specified.

## Quality gates

- Every new case is reviewed by at least one clinician.
- Baseline pass rate recorded in `eval/tier1/baseline.json`; CI
  fails the PR if the current pass rate drops below the baseline.
- Dataset size capped at 1000 cases to keep Tier 1 runtime under
  120s; the 500-case target is the sweet spot of coverage + speed.
