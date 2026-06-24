# Video Summary Prompt

Summarize the provided YouTube video transcript into a structured summary card.

Required output schema: `SummaryResult`.

## Rules

- `tldr`: ONE sentence capturing what the video is about and its most important conclusion.
- `key_points`: 3–6 key points. Every point MUST include a `timestamp` (seconds) drawn
  from the transcript markers provided. A point without a valid timestamp is invalid.
  `timestamp_str` is the `mm:ss` (or `h:mm:ss`) display form of that timestamp.
- `quotes`: 1–3 verbatim quotes from the transcript, each with its `timestamp`.
  Copy the wording exactly; do not paraphrase.
- `chapters`: echo the chapter list provided as input (title + start). If no chapters
  were provided, leave this empty.
- `tags`: 2–6 short topic tags (e.g. "AI", "大模型"). Use the video's own language.
- `transcript_source`: copy from the input (whether captions were manual or auto-generated).

## Anti-hallucination constraints

- Every `timestamp` MUST fall within the video's total duration given in the input.
  Never invent a timestamp that does not appear in the transcript.
- Every `quote` MUST be a substring of the provided transcript text.
- If the transcript is too short or garbled to summarize reliably, return a `tldr`
  explaining that and leave `key_points` / `quotes` empty rather than fabricating.

## Input format

The prompt receives:
1. The video title and total duration in seconds.
2. The transcript as a list of `[mm:ss] text` lines.
3. The chapter list (if any) as `mm:ss Title` lines.
4. The transcript source label (`manual` or `auto`).
