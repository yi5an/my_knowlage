# Entity Type Discovery Prompt

Suggest new entity types from the provided sample text using structured JSON only.

Required output schema: `EntityTypeSuggestionSchema`.

Rules:
- Suggestions are not active entity types.
- Include `evidence` and `confidence` for every suggestion.
- Use `suggested` status until a user confirms the type.
- Do not duplicate existing entity types.
