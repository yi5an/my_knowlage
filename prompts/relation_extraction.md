# Relation Extraction Prompt

Extract relations from known entities in the provided document chunk using structured JSON only.

Required output schema: `RelationExtractionSchema`.

Rules:
- Every relation must include `source_entity_id`, `target_entity_id`, `relation_type`, `evidence_text`, and `confidence`.
- Bind evidence to `evidence_doc_id` and `evidence_chunk_id` when available.
- Mark uncertain relations with low confidence instead of omitting evidence.
- Do not create graph database records.
