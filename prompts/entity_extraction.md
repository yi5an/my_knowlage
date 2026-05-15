# Entity Extraction Prompt

Extract entities from the provided document chunk using structured JSON only.

Required output schema: `EntityExtractionSchema`.

Rules:
- Include `evidence_text` copied from the source chunk.
- Include `confidence` between 0 and 1 for every entity.
- Normalize stock tickers to uppercase.
- Preserve aliases such as company names, short names, and ticker symbols.
- Do not invent entities that are not supported by the source text.
