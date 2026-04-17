# Labeled datasets for Afya Sahihi eval and training

This directory holds JSONL datasets used for model training and
evaluation. **None of the data is committed to the repo** — it is
produced from IRB-approved retrospective clinical logs and stored in
MinIO under `s3://afya-sahihi-corpus/datasets/`.

## Prefilter training set (`prefilter_train.jsonl`)

One row per labeled clinical query. Produced by the curation pipeline
described in issue #17 (IRB AKU-IRB-2026-0147).

### Schema

```json
{
    "query_text": "What is the first-line treatment for uncomplicated malaria in a child?",
    "intent": "malaria_dosing",
    "safety_flag": false,
    "language": "en",
    "source": "aku_retrospective"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query_text` | string | yes | The clinical query text. Must be PHI-scrubbed before labeling. |
| `intent` | string | yes | One of 42 canonical intent labels. See `intents.yaml`. |
| `safety_flag` | boolean | yes | `true` if the query requires the safety-critical slow path (dosing, contraindication, pediatric, pregnancy). |
| `language` | string | no | ISO 639-1 code. Default `"en"`. Supports `"sw"` (Swahili) and `"en-sw"` (code-switched). |
| `source` | string | no | Provenance tag. One of `aku_retrospective`, `synthetic`, `clinician_authored`. |

### Size requirements

- Minimum: 2000 rows (issue #17 lower bound)
- Target: 5000 rows
- Validation split: 20% held out, seeded from `config.seed`

### Quality checklist before training

- [ ] Every `query_text` has been PHI-scrubbed (run `app.validation.phi.scrub`)
- [ ] No duplicate `query_text` values
- [ ] Every `intent` is in the canonical 42-label set
- [ ] `safety_flag=true` rows are at least 15% of the total (class balance)
- [ ] At least 50 rows per language tag
