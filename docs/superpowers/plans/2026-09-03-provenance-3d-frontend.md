# Event–Conclusion Provenance True 3D Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent provenance page that renders the conclusion, event/fact/signal, and evidence layers in a genuine interactive WebGL scene with full path auditing and an explicit accessible fallback.

**Architecture:** Fetch the provenance API into typed page state; compute stable three-layer X/Z positions off the render path; render a Three.js perspective scene through React Three Fiber; keep camera, selection, filtering, and evidence details outside the renderer; use pure utilities for deterministic layout and visual mappings so most behavior is unit-testable, then prove real WebGL gestures and raycasting in Playwright.

**Tech Stack:** React 18, TypeScript 5.6, Vite 5, Three.js 0.180, `@react-three/fiber` 8.18, `@react-three/drei` 9.122, Ant Design, Vitest/jsdom, Playwright/Chromium.

---

## Scope and dependency boundary

Start after Tasks 1 and 7 of `2026-09-03-provenance-data-api.md` freeze the response schema and routes. This plan consumes those APIs and does not modify database models, provenance inference, or existing G6 entity-graph behavior.

The canonical design is `docs/superpowers/specs/2026-09-03-event-conclusion-provenance-3d-design.md`.

### Backend contract handoff

The schema and route implementation is frozen at backend commit `480a7f2` (with the full quality gate restored at `dc90e2b`). The frontend consumes these workspace-scoped routes:

- `GET /provenance/overview`
- `GET /provenance/nodes/{node_id}/trace?direction=up|down`
- `GET /provenance/edges/{edge_id}`
- `POST /provenance/edges/{edge_id}/review`
- `POST /provenance/conclusions`
- `POST /provenance/rebuild`
- `GET /provenance/jobs/{job_id}`

Graph responses expose `nodes`, canonical-direction `edges`, `clusters`, `graph_version`, degradation fields, and cursor metadata. Edge reviews require `version_no`; rebuild job responses expose durable `progress`, `output`, and failure state.

## Task 1: Install a React-18-compatible real 3D stack

**Files:**

- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [x] Add exact compatible runtime versions.

Run: `cd frontend && npm install three@0.180.0 @react-three/fiber@8.18.0 @react-three/drei@9.122.0`

Expected: npm exits 0 without React peer-dependency conflicts; the lockfile records one React 18 tree.

- [x] Verify the resolved peer graph.

Run: `cd frontend && npm ls react three @react-three/fiber @react-three/drei`

Expected: `react@18.3.1`, `three@0.180.0`, fiber `8.18.0`, and drei `9.122.0`, with no `invalid` marker.

- [x] Run the existing build before adding imports.

Run: `cd frontend && npm run build`

Expected: PASS.

- [x] Commit: `git add frontend/package.json frontend/package-lock.json && git commit -m "build: add provenance 3d dependencies"`

## Task 2: Mirror the backend contract in TypeScript

**Files:**

- Create: `frontend/src/types/provenance.ts`
- Create: `frontend/src/services/provenanceApi.ts`
- Create: `frontend/src/services/provenanceApi.test.ts`

- [x] Write failing request tests by mocking `apiRequest`. Cover overview filters, URL encoding, upward/downward trace, edge review with `version_no`, conclusion creation, rebuild, and job polling.

```ts
it("requests an upward trace without reversing stored edges", async () => {
  await provenanceApi.traceNode("event/1", "up", "ws_default");
  expect(apiRequest).toHaveBeenCalledWith(
    "/provenance/nodes/event%2F1/trace?workspace_id=ws_default&direction=up",
  );
});
```

- [x] Run: `cd frontend && npm run test -- src/services/provenanceApi.test.ts`

Expected: FAIL because the API module does not exist.

- [x] Define literal unions for all node layers/types, edge relations, review/validation statuses, evidence locators, graph metadata, filters, and review actions. Keep API field names in snake case rather than silently transforming them.

```ts
export type EvidenceLocator =
  | { type: "text_span"; chunk_id: string; start_offset: number; end_offset: number }
  | { type: "pdf_region"; page_no: number; bbox: [number, number, number, number] }
  | { type: "media_segment"; start_ms: number; end_ms: number }
  | { type: "image_region"; frame_id: string; bbox: [number, number, number, number]; ocr_block_ids: string[] }
  | { type: "web_fragment"; fragment_id: string; captured_at: string };

export interface ProvenanceGraphResponse {
  nodes: ProvenanceNode[];
  edges: ProvenanceEdge[];
  clusters: ProvenanceCluster[];
  graph_version: string;
  degraded: boolean;
  degraded_reason: string | null;
  total_nodes: number;
  returned_nodes: number;
  has_more: boolean;
  next_cursor: string | null;
}
```

- [x] Build query strings with `URLSearchParams`, omit undefined filters, and encode path IDs with `encodeURIComponent`.

- [x] Run: `cd frontend && npm run test -- src/services/provenanceApi.test.ts`

Expected: PASS.

- [x] Commit: `git add frontend/src/types/provenance.ts frontend/src/services/provenanceApi.ts frontend/src/services/provenanceApi.test.ts && git commit -m "feat: add provenance frontend contract"`

## Task 3: Implement deterministic three-layer layout in a worker

**Files:**

- Create: `frontend/src/components/provenance/layout.ts`
- Create: `frontend/src/components/provenance/layout.worker.ts`
- Create: `frontend/src/components/provenance/useProvenanceLayout.ts`
- Create: `frontend/src/components/provenance/layout.test.ts`

- [x] Write failing pure tests for stable coordinates, distinct seeds, fixed Y planes, finite positions, clustered spread, and unchanged positions when response ordering changes.

```ts
it("places every semantic layer on its fixed Y plane", () => {
  const result = computeProvenanceLayout(graphFixture, "v1|all");
  expect(result.get("conclusion-1")?.y).toBe(9);
  expect(result.get("event-1")?.y).toBe(0);
  expect(result.get("evidence-1")?.y).toBe(-9);
});
```

- [x] Run: `cd frontend && npm run test -- src/components/provenance/layout.test.ts`

Expected: FAIL.

- [x] Implement a deterministic 32-bit string hash and seeded PRNG. Sort nodes by ID before layout. Use `graph_version + serialized filters + node.id` as the seed input.

- [x] Arrange each layer into stable cluster rings in X/Z, then run a fixed-iteration collision relaxation constrained to that layer’s Y value. Do not use `Math.random()`.

- [x] Move `computeProvenanceLayout` invocation into `layout.worker.ts`. `useProvenanceLayout` must terminate the previous worker on graph/filter change and on unmount; provide a synchronous injectable adapter for unit tests.

- [x] Run: `cd frontend && npm run test -- src/components/provenance/layout.test.ts`

Expected: PASS.

- [x] Commit: `git add frontend/src/components/provenance/layout.ts frontend/src/components/provenance/layout.worker.ts frontend/src/components/provenance/useProvenanceLayout.ts frontend/src/components/provenance/layout.test.ts && git commit -m "feat: add deterministic provenance layout"`

## Task 4: Build the true WebGL scene and semantic visual mapping

**Files:**

- Create: `frontend/src/components/provenance/visualEncoding.ts`
- Create: `frontend/src/components/provenance/visualEncoding.test.ts`
- Create: `frontend/src/components/provenance/LayerPlane.tsx`
- Create: `frontend/src/components/provenance/InstancedNodes.tsx`
- Create: `frontend/src/components/provenance/TraceEdges.tsx`
- Create: `frontend/src/components/provenance/LabelLayer.tsx`
- Create: `frontend/src/components/provenance/ProvenanceScene.tsx`
- Create: `frontend/src/components/provenance/SpatialLayerCanvas3D.tsx`
- Create: `frontend/src/components/provenance/SpatialLayerCanvas3D.test.tsx`

- [x] Write failing tests for layer colors, relation colors/line styles, status glyphs, instance-ID-to-node mapping, selected-path opacity, and a mocked `Canvas` receiving a perspective camera rather than CSS transforms.

- [x] Run: `cd frontend && npm run test -- src/components/provenance/visualEncoding.test.ts src/components/provenance/SpatialLayerCanvas3D.test.tsx`

Expected: FAIL.

- [x] Implement pure `nodeVisual` and `edgeVisual` mappings. Encode state by color plus line style/glyph: confirmed solid, inference/pending dashed, refuted/conflict red with conflict marker, qualified amber.

- [x] Render translucent horizontal `LayerPlane` meshes at Y `9`, `0`, and `-9`; add labels “结论层”, “事件/事实层”, and “证据层”.

- [x] Render same-geometry nodes with one `InstancedMesh` per layer. Maintain an immutable `instanceId -> nodeId` array and resolve R3F `ThreeEvent<PointerEvent>.instanceId` through it.

```tsx
<instancedMesh
  ref={meshRef}
  args={[undefined, undefined, nodes.length]}
  onClick={(event) => {
    event.stopPropagation();
    const nodeId = event.instanceId === undefined ? undefined : instanceNodeIds[event.instanceId];
    if (nodeId) onSelectNode(nodeId);
  }}
>
  <sphereGeometry args={[0.34, 16, 12]} />
  <meshStandardMaterial vertexColors transparent />
</instancedMesh>
```

- [x] Render batched unselected edges and separately pickable selected/hovered edges. All coordinates must come from Three.js world space, not CSS `perspective`, `rotateX`, or DOM transforms.

- [x] Create `<Canvas frameloop="demand" camera={{ fov: 48, near: 0.1, far: 600, position: [22, 18, 28] }}>`; add ambient and directional light, call `invalidate()` only while transitions/particles run, and dispose custom geometry/material resources on unmount.

- [x] Expose `data-renderer="webgl"` and set `data-webgl-ready="true"` from `onCreated` only after `gl.info.render.frame >= 1` on the next frame. This marker supports diagnostics; it is not the sole browser assertion.

- [x] Run: `cd frontend && npm run test -- src/components/provenance/visualEncoding.test.ts src/components/provenance/SpatialLayerCanvas3D.test.tsx`

Expected: PASS.

- [x] Commit: `git add frontend/src/components/provenance && git commit -m "feat: render provenance in webgl"`

## Task 5: Add camera gestures, picking, focus, and reset

**Files:**

- Create: `frontend/src/components/provenance/cameraState.ts`
- Create: `frontend/src/components/provenance/cameraState.test.ts`
- Create: `frontend/src/components/provenance/CameraController.tsx`
- Modify: `frontend/src/components/provenance/ProvenanceScene.tsx`
- Modify: `frontend/src/components/provenance/SpatialLayerCanvas3D.tsx`

- [x] Write failing tests for distance limits, pitch limits, focus destination, URL serialization, keyboard deltas, reset state, and selection clearing.

- [x] Run: `cd frontend && npm run test -- src/components/provenance/cameraState.test.ts`

Expected: FAIL.

- [x] Implement pure camera-state serialization/parsing and focus transition helpers. Invalid URL values must return the default overview camera.

- [x] Configure `OrbitControls` with damping, `zoomToCursor`, min/max distance, polar angle limits, and the approved mouse mapping: left rotate; middle/right pan. Add a canvas key modifier so `Shift + left` temporarily changes the left action to pan and restores it on keyup/blur.

```tsx
<OrbitControls
  ref={controlsRef}
  makeDefault
  enableDamping
  zoomToCursor
  minDistance={6}
  maxDistance={90}
  minPolarAngle={0.18}
  maxPolarAngle={Math.PI - 0.18}
  mouseButtons={{
    LEFT: THREE.MOUSE.ROTATE,
    MIDDLE: THREE.MOUSE.PAN,
    RIGHT: THREE.MOUSE.PAN,
  }}
/>
```

- [x] Prevent the context menu only inside the 3D canvas. Do not change browser behavior elsewhere.

- [x] On node click, fetch/highlight its path and animate camera/target for about 450 ms. On edge click, open its audit record. On `onPointerMissed` double-click, reset the saved camera.

- [x] Add keyboard alternatives on a focusable canvas wrapper: arrows pan, `+/-` zoom, `R` reset, `Esc` clear selection. Update an `aria-live` summary after selection.

- [x] Persist camera state in URL search parameters after interaction settles, not every animation frame.

- [x] Run: `cd frontend && npm run test -- src/components/provenance/cameraState.test.ts src/components/provenance/SpatialLayerCanvas3D.test.tsx`

Expected: PASS.

- [x] Commit: `git add frontend/src/components/provenance && git commit -m "feat: control provenance camera and selection"`

## Task 6: Add path motion, LOD, and reduced-motion behavior

**Files:**

- Create: `frontend/src/components/provenance/FlowParticles.tsx`
- Create: `frontend/src/components/provenance/useMotionPreference.ts`
- Create: `frontend/src/components/provenance/scenePolicy.ts`
- Create: `frontend/src/components/provenance/scenePolicy.test.ts`
- Modify: `frontend/src/components/provenance/ProvenanceScene.tsx`
- Modify: `frontend/src/components/provenance/LabelLayer.tsx`

- [x] Write failing policy tests for label LOD thresholds, device-quality tiers, selected-path-only particles, automatic rotation defaulting off, and every animation disabled under reduced motion.

- [x] Run: `cd frontend && npm run test -- src/components/provenance/scenePolicy.test.ts`

Expected: FAIL.

- [x] Implement a pure scene policy from camera distance, node count, DPR, and reduced-motion preference. It may reduce labels/DPR/shadows/particles but must never remove a selected evidence path.

- [x] Animate only selected path particles in canonical evidence-to-conclusion direction. Use a red conflict/refutation treatment rather than reversing the stored edge direction.

- [x] Keep `frameloop="demand"`; call `invalidate()` while focus, entrance, optional auto-rotate, or active particles require frames. Stop invalidating when motion settles.

- [x] Use CSS/JS media query `prefers-reduced-motion: reduce` to disable entrance staggering, drift, particles, camera tweening, and auto-rotation. Selection and camera changes occur immediately.

- [x] Run: `cd frontend && npm run test -- src/components/provenance/scenePolicy.test.ts`

Expected: PASS.

- [x] Commit: `git add frontend/src/components/provenance && git commit -m "feat: add provenance motion and lod"`

## Task 7: Build auditing UI and explicit WebGL fallback

**Files:**

- Create: `frontend/src/components/provenance/TraceModeToolbar.tsx`
- Create: `frontend/src/components/provenance/GraphLegend.tsx`
- Create: `frontend/src/components/provenance/EvidenceLocatorLink.tsx`
- Create: `frontend/src/components/provenance/EvidenceAuditDrawer.tsx`
- Create: `frontend/src/components/provenance/ProvenanceFallbackView.tsx`
- Create: `frontend/src/components/provenance/webglSupport.ts`
- Create: `frontend/src/components/provenance/EvidenceAuditDrawer.test.tsx`
- Create: `frontend/src/components/provenance/ProvenanceFallbackView.test.tsx`

- [ ] Write failing tests for both trace modes, all state legend entries, stale evidence, exact text/PDF/media/image locators, edge metadata, review actions, conflict handling, and a visible “WebGL 不可用” fallback notice.

- [ ] Run: `cd frontend && npm run test -- src/components/provenance/EvidenceAuditDrawer.test.tsx src/components/provenance/ProvenanceFallbackView.test.tsx`

Expected: FAIL.

- [ ] Implement `supportsWebGL()` using a temporary canvas and both `webgl2` and `webgl` context probes. Keep the function injectable so tests do not depend on jsdom canvas support.

- [ ] Render a structured three-layer list/2D path in `ProvenanceFallbackView`. Label it as read-only fallback; do not apply CSS perspective or call it 3D.

- [ ] In `EvidenceAuditDrawer`, display quote, source snapshot, locator, freshness, confidence, relation rationale, model/prompt version, and review history. Enable review actions only when an edge and current `version_no` are loaded.

- [ ] Route locator links precisely:

  - text span: `/reader/{document_id}?chunk={chunk_id}&start={start_offset}&end={end_offset}`
  - PDF region: reader URL plus `page` and normalized bbox parameters
  - media segment: `/youtube/summary/{document_id}?start_ms={start_ms}&end_ms={end_ms}`
  - image region: video/document viewer plus frame and bbox parameters
  - web fragment: stored source snapshot details; never expose local storage paths

- [ ] On HTTP 409 review conflict, refetch the edge, keep the user note in the form, and show the newer version rather than retrying blindly.

- [ ] Run: `cd frontend && npm run test -- src/components/provenance/EvidenceAuditDrawer.test.tsx src/components/provenance/ProvenanceFallbackView.test.tsx`

Expected: PASS.

- [ ] Commit: `git add frontend/src/components/provenance && git commit -m "feat: add provenance audit and fallback"`

## Task 8: Assemble the page, route, and navigation

**Files:**

- Create: `frontend/src/pages/ProvenanceGraphPage.tsx`
- Create: `frontend/src/pages/ProvenanceGraphPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/styles.css`

- [ ] Write failing page tests for initial overview loading, URL-restored mode/filter/selection, upward/downward path fetches, degraded banner, partial result warning, empty/error states, fallback selection, and cleanup of stale requests.

- [ ] Add a failing route assertion that `/provenance` renders “事件结论溯源” and selects the new navigation item.

- [ ] Run: `cd frontend && npm run test -- src/pages/ProvenanceGraphPage.test.tsx src/App.test.tsx`

Expected: FAIL.

- [ ] Implement page state with `useReducer` and `AbortController`. Ignore out-of-order responses. Store shareable filter/mode/selection/camera state in URL parameters.

- [ ] Keep the canvas mounted while the audit drawer opens. Selection triggers the focused trace endpoint; closing the drawer returns to the overview only when the URL has no selected node/edge.

- [ ] Show a persistent degraded banner whenever `degraded=true`, including `degraded_reason`; never present the bounded fallback as a complete overview.

- [ ] Add the `/provenance` route and a “溯源图” navigation entry without changing `/graph` or `GraphCanvas`.

- [ ] Add responsive styles: full-height desktop canvas, overlay toolbar/legend, side drawer, and a usable small-screen list-first fallback.

- [ ] Run: `cd frontend && npm run test -- src/pages/ProvenanceGraphPage.test.tsx src/App.test.tsx`

Expected: PASS.

- [ ] Commit: `git add frontend/src/pages/ProvenanceGraphPage.tsx frontend/src/pages/ProvenanceGraphPage.test.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/styles.css && git commit -m "feat: add provenance graph page"`

## Task 9: Prove true 3D behavior in a real browser

**Files:**

- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/provenance-3d.spec.ts`
- Create: `frontend/e2e/fixtures/provenanceGraphs.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] Add `"test:e2e": "playwright test"` and configure Vite as Playwright’s web server on a fixed test port.

- [ ] Add a deterministic API fixture route for 100, 500, and 2000 raw-node responses. The browser test must not require a live backend.

- [ ] Add a development/test-only scene probe exposing copies of renderer/camera/control state through `window.__KNOWPILOT_PROVENANCE_DEBUG__`. Do not expose mutable Three.js objects.

```ts
interface ProvenanceDebugSnapshot {
  renderer: "WebGLRenderer";
  frame: number;
  cameraPosition: [number, number, number];
  cameraQuaternion: [number, number, number, number];
  controlsTarget: [number, number, number];
  selectedNodeId: string | null;
  geometries: number;
  textures: number;
}
```

- [ ] Write browser assertions that prove behavior, not just appearance:

```ts
test("rotates, pans, zooms, raycasts, and resets in WebGL", async ({ page }) => {
  await page.goto("/provenance?fixture=100");
  await expect(page.locator('[data-webgl-ready="true"]')).toBeVisible();
  const before = await debugSnapshot(page);
  await dragCanvas(page, { button: "left", dx: 120, dy: 30 });
  expect((await debugSnapshot(page)).cameraQuaternion).not.toEqual(before.cameraQuaternion);
  await dragCanvas(page, { button: "right", dx: 80, dy: 0 });
  expect((await debugSnapshot(page)).controlsTarget).not.toEqual(before.controlsTarget);
  await page.locator("[data-provenance-canvas]").hover();
  await page.mouse.wheel(0, -480);
  expect(distanceToTarget(await debugSnapshot(page))).toBeLessThan(distanceToTarget(before));
});
```

- [ ] Also assert WebGL renderer construction, at least one rendered frame, node raycast selection updating the audit drawer, edge selection, Shift-left pan, middle pan, double-click reset, keyboard alternatives, reduced motion, explicit no-WebGL fallback, resource counts after mount/unmount, and selected-path completeness for the 2000-node fixture.

- [ ] Run: `cd frontend && npm run test:e2e -- e2e/provenance-3d.spec.ts`

Expected: PASS in Chromium with hardware or SwiftShader WebGL.

- [ ] Commit: `git add frontend/playwright.config.ts frontend/e2e frontend/package.json frontend/package-lock.json frontend/src/components/provenance && git commit -m "test: verify provenance webgl interactions"`

## Task 10: Frontend regression and documentation

**Files:**

- Modify: `README.md`
- Modify: `docs/development/testing-guide.md`

- [ ] Document the controls exactly: left rotate; Shift-left/middle/right pan; wheel cursor zoom; single-click focus; double-click empty reset; arrows/plus/minus/R/Escape keyboard controls.

- [ ] Document GPU adaptation, reduced-motion behavior, and the visible WebGL fallback.

- [ ] Run the complete frontend quality gate:

Run: `cd frontend && npm run lint && npm run test && npm run build && npm run test:e2e`

Expected: all commands exit 0.

- [ ] Manually inspect desktop and narrow viewport layouts against 100- and 2000-node fixtures. Confirm the selected path remains legible, labels do not cover the audit drawer, and status is not encoded by color alone.

- [ ] Commit: `git add README.md docs/development/testing-guide.md && git commit -m "docs: document provenance 3d controls"`

## Implementation completion criteria

- Browser diagnostics identify a Three.js `WebGLRenderer`; no CSS transform is used to simulate scene depth.
- Perspective, occlusion, camera quaternion changes, control-target changes, zoom distance, and raycaster selection are proven in Chromium.
- All approved mouse and keyboard controls work and remain bounded.
- All conclusion, event/fact/signal, evidence, relation, validation, review, conflict, and stale states are inspectable.
- WebGL failure and graph-store degradation are visible and honest.
- Frontend lint, unit tests, production build, and browser tests pass.
