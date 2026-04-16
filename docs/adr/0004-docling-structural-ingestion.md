# ADR-0004: Docling with structural metadata on every chunk

**Status:** Accepted
**Date:** 2026-04-16
**Deciders:** Ezra O'Marley

## Context

In Kenyan Ministry of Health clinical guidelines, the visual hierarchy is the clinical hierarchy. Bold red boxes mark contraindications. Indented sub-bullets carry pediatric dose adjustments. Tables encode drug-drug interactions. Section headings define the scope of every statement they contain.

Afya Gemma v1 flattened these PDFs into plain text chunks. The flattening discarded exactly the signals that a clinician would use to interpret the document. Several retrieval bugs (including the adrenaline-to-malaria mismatch) were rooted in chunks that looked semantically similar in embedding space but came from incompatible clinical contexts.

The revised architecture treats document structure as first-class data.

## Decision

All PDF ingestion uses Docling's HybridChunker with structural metadata preservation. Every chunk carries a JSONB payload:

```json
{
  "source": {
    "document_id": "moh-malaria-guidelines-v7",
    "document_hash": "sha256:...",
    "page_range": [42, 43],
    "bounding_boxes": [{"page": 42, "x0": 72, "y0": 120, "x1": 540, "y1": 310}]
  },
  "structure": {
    "section_path": ["Malaria", "Treatment", "Uncomplicated", "Pediatric"],
    "heading_level": 4,
    "parent_table_id": null,
    "visual_emphasis": ["bold", "red_box"],
    "list_depth": 2,
    "is_contraindication": true
  },
  "content_type": "text",
  "language": "en",
  "extraction_version": "docling-2.9.0"
}
```

Tables are chunked as atomic units, not row-by-row. Captions are co-chunked with their tables. Figures are captured with their caption text and alt text.

This metadata is queryable alongside the dense vector and BM25 search. A retrieval can say "only return chunks where `structure.is_contraindication = true` for any dosing query."

## Consequences

**Positive**

- Retrieval precision on structural queries ("what are the contraindications for X") improves significantly because we can filter rather than hope the embedding caught the signal.
- Every generated response can cite not just a document but a specific region: document, page, bounding box. Provenance becomes verifiable.
- The DocMason thesis (that answers must be strictly traceable to file-based evidence) is implemented at the chunk level without adopting the DocMason product.
- Clinical reviewers can click any citation in the UI and see the exact highlighted region of the source PDF. This is a major trust artifact.

**Negative**

- Ingestion is slower. Docling with full structural extraction runs roughly 4x slower than PyPDF2 text extraction. For our corpus (approximately 500 PDFs, reingested quarterly) this is acceptable.
- The chunks table schema is wider. Postgres handles this fine.
- Chunking logic is now domain-aware and needs testing against representative MoH PDFs.

**Neutral**

- Docling version pinned. We do not auto-upgrade; the extraction output format is part of our data contract.

## Alternatives considered

- **PyPDF2 / pdfplumber**: fast but structurally blind.
- **Unstructured.io**: good structural extraction, but licensing and dependency weight are problematic.
- **LlamaParse**: cloud-based, sends documents to a third party. Unacceptable for PHI-adjacent ingestion even when the documents themselves are public.
- **DocMason (the product)**: adopts a Codex runtime dependency we do not want. We take its thesis without its implementation.
- **GROBID**: excellent for academic papers, weaker on clinical guidelines.

## Compliance and references

- Docling pinned to version 2.9.0 in `requirements.txt`
- Ingestion is an offline job, not on the request path
- Re-ingestion triggers: new PDF added, hash change on existing PDF, Docling version bump (with manual re-review)
- Related: ADR-0002 (Postgres consumes this metadata)
