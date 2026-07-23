# Global AI Companion Design

## Goal

Replace the reader-only companion with a persistent, evidence-grounded AI
companion that works from any KnowPilot content page. The first release covers
documents, YouTube video summaries, and information-edge items.

## Product Experience

The application shell provides one floating `AI 陪读` entry. Opening it reveals
a right-side drawer with the active context shown as a pill. The drawer has:

1. proactive insights for the active content;
2. a persistent conversation for questions and follow-ups;
3. source citations, excerpts, and confidence on every generated conclusion;
4. an action to start a new conversation while retaining prior sessions.

When no specific content object is active, the drawer supports general
workspace Q&A only and does not generate proactive insights.

## Context Model

The frontend supplies a typed context descriptor instead of page-specific
prompt logic:

```text
workspace_id
subject_type: document | youtube_video | information_edge | workspace
subject_id: stable database identifier, or workspace id for workspace context
title
route
selection: optional selected text, chunk, or information-edge item
```

Context adapters resolve content for each supported page:

- Reader: active document and optional selected chunk/text.
- YouTube summary: summary document/video and its transcript, visual evidence,
  key points, and source traces.
- Information edge: selected edge item; if none is selected, the current page
  filters form a workspace-level context.

Future pages register an adapter and use the same drawer, session API, and
evidence rendering.

## Backend Domain

Introduce a generic companion domain rather than extending `ReadingAnalysis`:

- `companion_session`: one saved conversation for a workspace and subject,
  with a title and lifecycle status.
- `companion_message`: user, assistant, or system message, with structured
  citations and confidence.
- `companion_insight`: background-generated focus, question, opportunity, or
  risk insight for a subject, with evidence and review status.
- `task_job`: existing asynchronous job mechanism runs proactive analysis and
  records progress/failure.

The existing reading-analysis records remain readable during migration, but
new companion work uses the generic domain.

## Retrieval and Evidence

Every request starts with the active subject's material. It then searches the
current workspace for corroborating or conflicting internal material. The
model receives structured evidence objects containing source title, source
identifier, excerpt, location, relation (`primary`, `corroborates`,
`conflicts`), and confidence.

Responses must use structured output and persist citations. If no relevant
internal evidence exists, the assistant explicitly states that the conclusion
is based only on the active subject or cannot be corroborated.

## Proactive Analysis

On the first visit to a subject, the UI creates or reuses a background
analysis task. It generates a small bounded set of:

- key focus points;
- unresolved questions;
- risks or opportunities when appropriate;
- suggested follow-up questions.

Repeated visits reuse the completed result. A user may explicitly refresh it,
which creates a new task and preserves the prior successful insights until a
new result succeeds.

## APIs

The generic API surface is scoped under `/api/v1/companion`:

- create/list/get sessions by subject;
- submit a message and retrieve the persisted assistant response;
- create/get proactive analysis status;
- confirm or dismiss an insight;
- retrieve an evidence citation by source identifier.

All APIs validate workspace ownership and subject type before loading context.

## UI Integration

`App.tsx` owns the drawer and a companion context provider. Content pages only
set or clear their context. The drawer is not duplicated inside Reader,
VideoSummaryPage, or InformationEdgePage.

The existing Reader right rail is simplified to a button that opens the global
drawer in document context, preserving familiar entry while preventing two
competing companion interfaces.

## Error Handling

- Context unavailable: show a clear unavailable state and do not create a
  session.
- Retrieval returns no evidence: allow the answer but label it as uncorroborated.
- Model or background task fails: preserve prior completed insights and expose
  a retry action with the task error.
- A stale route/context change cancels client polling and does not append an
  answer to the new subject's session.

## Acceptance Criteria

1. A user can open one global drawer from Reader, YouTube video detail, and
   information-edge pages.
2. The drawer automatically identifies the active subject and saves separate
   sessions per subject.
3. Assistant answers and proactive insights show internal evidence and
   confidence, or explicitly state missing corroboration.
4. Proactive analysis runs asynchronously and is reusable, refreshable, and
   non-destructive.
5. All new schemas, service modules, APIs, React components, and adapters have
   focused tests; backend and frontend quality suites pass.
