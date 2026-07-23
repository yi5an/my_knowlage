# Ignore Live YouTube Videos Design

## Goal

Keep scheduled and currently live YouTube broadcasts out of KnowPilot. They
must not create video rows, summary jobs, or entries in YouTube history.

## Classification

The YouTube Data API already returns `snippet.liveBroadcastContent` for video
metadata. The fetcher will expose that value as a typed field on `VideoMeta`.

- `upcoming`: scheduled broadcast; ignore.
- `live`: broadcast currently in progress; ignore.
- `none`: ordinary uploaded video or completed livestream replay; process as
  normal.

The implementation must not use ASR or caption error text as the primary
classifier. Those errors occur after unnecessary work has already begun and
are not a stable API contract.

## Processing Rules

### Channel discovery

Channel polling filters `upcoming` and `live` videos before persistence. No
`Video`, `Document`, or `TaskJob` is created for either state.

### Manual requests

Manual single-video requests apply the same metadata classification before a
durable summary job is queued. The API returns a successful ignored response
that the frontend can present as a non-error notification.

### Existing historical rows

Rows created before this change may already have an ASR/caption failure caused
by a scheduled broadcast. They are reclassified to `ignored_live`, removed
from normal summary history, and excluded from all automatic retries. Existing
documents are not deleted.

## API and UI

The summary-history API excludes `ignored_live` records. The frontend does not
render a history card or retry action for ignored live broadcasts. Manual
submission reports that the video was ignored because it is scheduled or live,
instead of reporting a transcription failure.

## Error Handling

If the YouTube metadata request itself fails, existing error behavior remains
unchanged. A completed livestream replay identified as `none` is never
suppressed.

## Tests

- Fetcher maps `liveBroadcastContent` into typed metadata.
- Channel discovery does not persist or queue `upcoming`/`live` videos.
- Manual video submission does not enqueue a job for an ignored live video.
- Existing live-related failed rows become `ignored_live` and the retry scanner
  skips them.
- History responses exclude `ignored_live`; `none` videos remain visible.
