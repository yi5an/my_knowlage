# 观察对象信息源引导 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an observation object the primary setup entry point by allowing users to bind existing sources, create configured sources, and start their initial fetch from one guided flow.

**Architecture:** Keep the existing FastAPI binding, source-creation, and asynchronous polling APIs unchanged. Extract source-payload construction from the global source page into a typed frontend helper, then use that helper in the global page and the watchlist wizard. The watchlist page owns the two-step wizard, per-source operation status, and object-detail source actions.

**Tech Stack:** React 18, TypeScript, Ant Design 5, React Testing Library, Vitest, existing `investmentApi` client.

---

## File structure

- Create: `frontend/src/components/investment/sourcePayload.ts` — source-type labels, defaults, configuration validation, and `CreateSourcePayload` construction shared by both source entry points.
- Create: `frontend/src/components/investment/sourcePayload.test.ts` — unit tests for every source configuration path used by the onboarding flow.
- Modify: `frontend/src/pages/InvestmentSourcesPage.tsx` — replace its local payload-building branch with the shared helper; retain global source-management UI.
- Modify: `frontend/src/pages/InvestmentWatchlistPage.tsx` — add the two-step creation wizard, existing-source binding, configured-source creation, fetch-result feedback, and detail-level source actions.
- Modify: `frontend/src/pages/InvestmentWatchlistPage.test.tsx` — retain current detail-tab coverage and add UI/API orchestration tests for the new flows.
- Create: `docs/superpowers/specs/2026-07-17-watchlist-source-onboarding-design.md` — already committed design source of truth; no changes planned unless implementation reveals a contradiction.

No backend file changes are expected: `POST /investment/watchlist`, `POST /investment/watchlist/{watchlist_id}/sources/{source_id}`, `POST /investment/sources`, and `POST /investment/sources/{source_id}/poll` already support the required flow.

### Task 1: Extract and test source payload construction

**Files:**

- Create: `frontend/src/components/investment/sourcePayload.ts`
- Create: `frontend/src/components/investment/sourcePayload.test.ts`
- Modify: `frontend/src/pages/InvestmentSourcesPage.tsx:24-180`

- [ ] **Step 1: Write the failing payload-helper tests**

Create `sourcePayload.test.ts` with tests that define the supported source configurations and required fields:

```ts
import { describe, expect, it } from "vitest";
import { buildSourcePayload, SourcePayloadError } from "./sourcePayload";

describe("buildSourcePayload", () => {
  it("builds an SEC source with a mandatory CIK and default filing forms", () => {
    expect(
      buildSourcePayload({
        source_type: "sec_edgar",
        name: "NVIDIA SEC",
        cik: "0001045810",
        default_watchlist_ids: ["wl_nvda"],
      }),
    ).toMatchObject({
      source_type: "sec_edgar",
      config: { cik: "0001045810", forms: ["10-K", "10-Q", "8-K", "4"] },
      default_watchlist_ids: ["wl_nvda"],
      default_info_layer: "news",
      poll_interval_seconds: 3600,
    });
  });

  it("builds an account X web source with an opinion layer and 15-minute interval", () => {
    expect(
      buildSourcePayload({ source_type: "x_web", name: "NVIDIA X", x_username: "@nvidia" }),
    ).toMatchObject({
      source_type: "x_web",
      config: { mode: "account", username: "nvidia", max_items_per_poll: 50 },
      default_info_layer: "opinion",
      poll_interval_seconds: 900,
    });
  });

  it("rejects selected templates that lack their required configuration", () => {
    expect(() =>
      buildSourcePayload({ source_type: "sec_edgar", name: "NVIDIA SEC" }),
    ).toThrow(new SourcePayloadError("SEC EDGAR 需要填写 CIK"));
    expect(() =>
      buildSourcePayload({ source_type: "rss", name: "公司公告" }),
    ).toThrow(new SourcePayloadError("RSS / Atom 需要填写 URL"));
  });
});
```

- [ ] **Step 2: Run the focused helper test and verify RED**

Run: `cd frontend && npm run test -- --run src/components/investment/sourcePayload.test.ts`

Expected: FAIL because `./sourcePayload` does not exist.

- [ ] **Step 3: Implement the typed helper**

Create `sourcePayload.ts` with these public types and single construction function:

```ts
import type { CreateSourcePayload, InfoLayer, SourceType } from "../../services/investmentApi";

export class SourcePayloadError extends Error {}

export interface SourceDraftValues {
  source_type: SourceType;
  name: string;
  url?: string;
  cik?: string;
  series?: string | string[];
  years?: number;
  limit?: number;
  profile_urls?: string | string[];
  x_web_mode?: "account" | "keyword";
  x_username?: string;
  x_keyword?: string;
  x_target?: string;
  x_base_url?: string;
  default_info_layer?: InfoLayer;
  default_watchlist_ids?: string[];
  poll_interval_seconds?: number;
}

export function buildSourcePayload(values: SourceDraftValues): CreateSourcePayload {
  // Trim name; throw SourcePayloadError when a required value is empty.
  // Use the existing source-page defaults: X web 900 seconds, Bright Data 21600,
  // all other types 3600; X-derived sources use the opinion layer.
  // Preserve the current config shapes for sec_edgar, bls, fred, x_brightdata,
  // x_web, x_rss/x_nitter, and URL-backed sources.
}
```

Implement local helpers `splitValues(raw: string | string[] | undefined): string[]` and `required(value: unknown, message: string): string`. Their required error messages must be: `SEC EDGAR 需要填写 CIK`, `RSS / Atom 需要填写 URL`, `X 网页采集需要填写 X 用户名`, `X 关键词采集需要填写关键词`, `BLS 需要填写至少一个序列 ID`, and `FRED 需要填写至少一个序列 ID`. Retain the existing page’s source configuration semantics exactly, including stripping a leading `@` from X usernames.

- [ ] **Step 4: Replace the global page’s local construction code**

In `InvestmentSourcesPage.tsx`, remove `_splitSeries` and the `handleCreate` `if/else` payload branch. Replace it with:

```ts
const payload = buildSourcePayload({
  ...values,
  source_type: values.source_type as SourceType,
  default_watchlist_ids: values.watchlist_ids ?? [],
});
await investmentApi.createSource(payload);
```

Catch `SourcePayloadError` in the existing error path so the Ant Design message displays the Chinese validation error. Keep the existing dynamic source fields and all table/polling behavior unchanged.

- [ ] **Step 5: Run the helper and existing global source tests**

Run:

```bash
cd frontend
npm run test -- --run src/components/investment/sourcePayload.test.ts src/pages/InvestmentSourcesPage.test.tsx
```

Expected: PASS. If `InvestmentSourcesPage.test.tsx` is absent, run the helper test alone and record that the global page has no existing dedicated test file.

- [ ] **Step 6: Commit the helper extraction**

```bash
git add frontend/src/components/investment/sourcePayload.ts \
  frontend/src/components/investment/sourcePayload.test.ts \
  frontend/src/pages/InvestmentSourcesPage.tsx
git commit -m "refactor: share investment source payload builder"
```

### Task 2: Add source-management actions to an existing observation object

**Files:**

- Modify: `frontend/src/pages/InvestmentWatchlistPage.tsx:1-155, 280-410`
- Modify: `frontend/src/pages/InvestmentWatchlistPage.test.tsx`

- [ ] **Step 1: Write the failing detail-source interaction test**

Add a test whose fetch mock returns watchlist `wl_nvda`, bound source `src_sec`, and available unbound source `src_rss`. Make the test:

```ts
fireEvent.click(await screen.findByRole("button", { name: "绑定已有信息源" }));
fireEvent.mouseDown(screen.getByLabelText("选择已有信息源"));
fireEvent.click(await screen.findByText("NVIDIA IR RSS"));
fireEvent.click(screen.getByRole("button", { name: "绑定" }));

await waitFor(() => {
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringContaining("/investment/watchlist/wl_nvda/sources/src_rss"),
    expect.objectContaining({ method: "POST" }),
  );
});
```

Then click `立即抓取` for `src_sec` and assert a `POST` request to `/investment/sources/src_sec/poll`.

- [ ] **Step 2: Run the focused page test and verify RED**

Run: `cd frontend && npm run test -- --run src/pages/InvestmentWatchlistPage.test.tsx`

Expected: FAIL because the detail page does not render `绑定已有信息源` or source-level `立即抓取` controls.

- [ ] **Step 3: Implement existing-source binding and per-source poll actions**

In `InvestmentWatchlistPage.tsx`:

1. Add state for `bindSourceOpen`, `bindingSourceIds: string[]`, `pollingSourceIds: Record<string, boolean>`, and a dedicated Ant Design form for binding.
2. Add a `绑定已有信息源` button above `renderSourceList()` when a watchlist is selected. Its select options are `sources` excluding `detailSources` and it supports multiple selection.
3. Submit each selected ID with `Promise.allSettled(investmentApi.bindWatchlistSource(selectedWatchlistId, id))`. Show a success count and error message; refresh both `load()` and detail data after completion.
4. Render each bound source’s `last_error` below its interval and add an `立即抓取` button. Its handler calls `investmentApi.pollSource(source.id)`, marks only that source busy, then refreshes detail/global source data; it does not claim that the background job has succeeded.
5. Keep the existing unlink action available from the detail list as a small `解绑` button, rather than only from tags in the left list. Task 4 adds the detail-level `新建并绑定` modal after the wizard has established its reusable draft UI.

Use `message.error` only for user-visible API errors; do not silently ignore individual `Promise.allSettled` rejections.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `cd frontend && npm run test -- --run src/pages/InvestmentWatchlistPage.test.tsx`

Expected: PASS, including the original detail tab test and the new binding/poll test.

- [ ] **Step 5: Commit detail source management**

```bash
git add frontend/src/pages/InvestmentWatchlistPage.tsx \
  frontend/src/pages/InvestmentWatchlistPage.test.tsx
git commit -m "feat: manage sources from watchlist details"
```

### Task 3: Add the two-step observation-object onboarding wizard

**Files:**

- Modify: `frontend/src/pages/InvestmentWatchlistPage.tsx:20-410`
- Modify: `frontend/src/pages/InvestmentWatchlistPage.test.tsx`

- [ ] **Step 1: Write the failing existing-source onboarding test**

Add a test for the standard path that opens `添加观察对象`, fills step 1, advances to `配置首批信息源`, selects existing source `src_rss`, and finishes. The mock must return a new watchlist:

```ts
{
  id: "wl_nvda",
  workspace_id: "ws_default",
  name: "NVIDIA",
  watch_type: "stock",
  keywords: ["AI", "数据中心"],
  importance: "high",
  enabled: true,
}
```

Assert calls occur in this observable order: `POST /investment/watchlist`, `POST /investment/watchlist/wl_nvda/sources/src_rss`, and `POST /investment/sources/src_rss/poll`. Then assert that the page shows `NVIDIA 详情`, the active tab is `最新信息`, and a visible setup result says `NVIDIA IR RSS：抓取中`.

- [ ] **Step 2: Run the focused page test and verify RED**

Run: `cd frontend && npm run test -- --run src/pages/InvestmentWatchlistPage.test.tsx`

Expected: FAIL because the current modal has one step and cannot select an existing source before creating the object.

- [ ] **Step 3: Implement the step state and existing-source orchestration**

Replace `open` with `onboardingOpen`, extract the current detail-fetch effect into a `loadDetails(watchlistId: string)` callback so that action handlers can refresh it explicitly, and add:

```ts
type OnboardingStep = "details" | "sources";
type SetupResult = {
  key: string;
  sourceName: string;
  state: "bound" | "created" | "fetching" | "failed";
  error?: string;
  retry?:
    | { kind: "bind"; watchlistId: string; sourceId: string }
    | { kind: "create"; watchlistId: string; draft: SourceDraftValues }
    | { kind: "poll"; sourceId: string };
};
```

Use one `Form` with fields `name`, `watch_type`, `ticker`, `exchange`, `importance`, `keywords`, `notes`, `existing_source_ids`, and `source_drafts`. On the first primary action, run `form.validateFields(["name", "watch_type", "ticker", "exchange", "importance", "keywords", "notes"])`, then set the step to `sources` without creating a server record. On the final action:

1. Call `investmentApi.createWatchlist` with the existing object fields and trimmed comma-separated keywords.
2. Bind selected existing sources with `Promise.allSettled`.
3. Create valid drafts using `investmentApi.createSource(buildSourcePayload({ ...draft, default_watchlist_ids: [created.id] }))`.
4. Call `investmentApi.pollSource` for every successfully bound or created source and add a `fetching` result immediately after its request resolves.
5. Set `selectedWatchlistId` to `created.id`, set the controlled details `Tabs` active key to `items`, refresh list/detail data, close the wizard, and render a dismissible `首批信息源设置结果` card above the detail tabs.

The object must remain visible if any subsequent source operation fails. Add failed result rows that show the source name and API error with a `重试` button. Implement `retrySetupResult(result: SetupResult)` by switching on `result.retry.kind`: repeat one bind with its stored IDs, recreate one source from its stored `SourceDraftValues`, or requeue one poll with its stored source ID; do not rerun the entire wizard.

- [ ] **Step 4: Run the onboarding path test and verify GREEN**

Run: `cd frontend && npm run test -- --run src/pages/InvestmentWatchlistPage.test.tsx`

Expected: PASS, with the new test proving creation, binding, poll enqueue, selected object, active latest-information tab, and visible fetching result.

- [ ] **Step 5: Commit the existing-source onboarding path**

```bash
git add frontend/src/pages/InvestmentWatchlistPage.tsx \
  frontend/src/pages/InvestmentWatchlistPage.test.tsx
git commit -m "feat: onboard watchlists with existing sources"
```

### Task 4: Add explicit source templates and custom-source validation to onboarding

**Files:**

- Modify: `frontend/src/pages/InvestmentWatchlistPage.tsx`
- Modify: `frontend/src/pages/InvestmentWatchlistPage.test.tsx`

- [ ] **Step 1: Write failing template and validation tests**

Add two tests:

```ts
it("blocks a selected SEC template until its CIK is provided", async () => {
  // Complete object step, select “SEC EDGAR”, leave CIK empty, and click 完成并开始抓取.
  // Assert the page displays “SEC EDGAR 需要填写 CIK” and fetch was never called for /investment/sources.
});

it("creates a configured X template bound to the new watchlist and queues its fetch", async () => {
  // Select “官方 X”, fill @nvidia, complete onboarding.
  // Assert POST /investment/sources contains:
  // { source_type: "x_web", name: "官方 X · @nvidia",
  //   default_watchlist_ids: ["wl_nvda"],
  //   config: { mode: "account", username: "nvidia", max_items_per_poll: 50 } }
  // Assert the returned source ID is then posted to /investment/sources/{id}/poll.
});
```

- [ ] **Step 2: Run the focused page test and verify RED**

Run: `cd frontend && npm run test -- --run src/pages/InvestmentWatchlistPage.test.tsx`

Expected: FAIL because the wizard does not yet render source templates or field-level required configuration.

- [ ] **Step 3: Implement template selection and custom-source input**

Define a local `sourceTemplatesForWatchType` mapping in `InvestmentWatchlistPage.tsx`:

```ts
const sourceTemplatesForWatchType = {
  stock: ["sec_edgar", "rss", "x_web"],
  company: ["sec_edgar", "rss", "x_web"],
  macro: ["federal_reserve_rss", "bls", "fred", "x_web"],
  etf: ["rss", "x_web"],
} as const;
```

On step 2, render:

1. a multi-select for existing sources;
2. checkbox cards for source templates allowed by the selected `watch_type`;
3. a `Form.List name="source_drafts"` row for each selected template, with a default display name and only the needed inputs:
   - `sec_edgar`: `cik`;
   - `rss` and `federal_reserve_rss`: `url`;
   - `x_web`: radio/select for `x_web_mode`, then `x_username` or `x_keyword`;
   - `bls` and `fred`: `series`, with BLS `years` and FRED `limit`;
4. an `添加自定义来源` button which appends a draft with a `source_type` select and renders the same conditional fields.

Before creating any record, run `buildSourcePayload` over every selected draft. Catch `SourcePayloadError`, attach the exact message to the matching draft row using `form.setFields`, and stop before `createWatchlist` so invalid source configuration cannot create a partially configured object.

Use the helper’s output unchanged; only append `default_watchlist_ids: [created.id]` after the object exists. Do not create suggested sources unless the user selected their cards.

Also add `新建并绑定` to the object-detail source tab. It opens a modal containing one `source_drafts` entry and reuses the same draft fields/validation. After `buildSourcePayload` succeeds, call `investmentApi.createSource({ ...payload, default_watchlist_ids: [selectedWatchlistId] })`, refresh detail/global source data, and offer immediate poll with the same source-level action introduced in Task 2.

- [ ] **Step 4: Run template, helper, and page tests and verify GREEN**

Run:

```bash
cd frontend
npm run test -- --run \
  src/components/investment/sourcePayload.test.ts \
  src/pages/InvestmentWatchlistPage.test.tsx
```

Expected: PASS. The test must verify both no API creation when a selected template is invalid and the exact source payload/poll request for a valid X template.

- [ ] **Step 5: Commit template onboarding**

```bash
git add frontend/src/pages/InvestmentWatchlistPage.tsx \
  frontend/src/pages/InvestmentWatchlistPage.test.tsx
git commit -m "feat: configure source templates during watchlist onboarding"
```

### Task 5: Full verification and documentation check

**Files:**

- Verify: `frontend/src/components/investment/sourcePayload.ts`
- Verify: `frontend/src/components/investment/sourcePayload.test.ts`
- Verify: `frontend/src/pages/InvestmentSourcesPage.tsx`
- Verify: `frontend/src/pages/InvestmentWatchlistPage.tsx`
- Verify: `frontend/src/pages/InvestmentWatchlistPage.test.tsx`
- Verify: `docs/superpowers/specs/2026-07-17-watchlist-source-onboarding-design.md`

- [ ] **Step 1: Run the complete frontend test suite**

Run: `cd frontend && npm run test`

Expected: PASS, with no test regressions outside the new onboarding coverage.

- [ ] **Step 2: Run frontend static checks and production build**

Run:

```bash
cd frontend
npm run lint
npm run build
```

Expected: both commands exit 0.

- [ ] **Step 3: Manually exercise the partial-failure contract**

Run the frontend against the local backend. Create an object with one valid existing source and one new source whose server configuration is deliberately invalid (for example a SEC source when `SEC_USER_AGENT` is absent). Confirm the object and valid binding remain, the invalid fetch outcome is shown with its error, and `重试` targets only the failed source operation.

- [ ] **Step 4: Reconcile implementation with the approved specification**

Check every acceptance criterion in `docs/superpowers/specs/2026-07-17-watchlist-source-onboarding-design.md` against the completed UI and tests. If the implementation requires a semantic change, update the spec in the same commit and describe the reason in the commit body.

- [ ] **Step 5: Commit final verification/doc changes if needed**

```bash
git status --short
git add docs/superpowers/specs/2026-07-17-watchlist-source-onboarding-design.md
git commit -m "docs: finalize watchlist source onboarding"
```

Only run this commit if Step 4 changed the design document. Do not stage unrelated `.DS_Store`, `.superpowers/`, or pre-existing untracked plan files.
