# Provenance Contrast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the event-conclusion provenance 3D view readable in the selected C / light-analysis direction without changing graph behavior.

**Architecture:** Keep the existing Three.js scene, layout, camera controls, and API unchanged. Introduce one shared high-contrast palette for layer planes and node/edge encoding, then update the CSS shell around the canvas so controls, labels, nodes, and legend use a light-card treatment on a pale blue-gray stage.

**Tech Stack:** React, TypeScript, Three.js / React Three Fiber, CSS, Vitest, Playwright, Vite.

---

### Task 1: Freeze the light-analysis palette in tests

**Files:**
- Modify: `frontend/src/components/provenance/visualEncoding.test.ts`
- Modify: `frontend/src/components/provenance/LayerPlane.test.tsx` (create if absent)
- Create: `frontend/src/components/provenance/provenancePalette.ts`
- Test: `frontend/src/components/provenance/provenancePalette.test.ts`

- [x] **Step 1: Write failing palette tests**

  Add tests that assert the three layer colors are distinct dark colors suitable for pale backgrounds, plane colors are distinct translucent companion colors, and status colors remain semantically distinct. The assertions should use exported palette values so later scene and CSS code share the same source of truth.

- [x] **Step 2: Run the focused tests and verify they fail**

  Run `cd frontend && npm run test -- provenancePalette.test.ts visualEncoding.test.ts --run`.

  Expected: FAIL because `provenancePalette.ts` does not exist and the current visual encoding still returns the old saturated blue/purple/teal values.

- [x] **Step 3: Add the shared palette and update visual encoding**

  Create a typed palette with:

  ```ts
  export const PROVENANCE_PALETTE = {
    stage: { background: "#eef2f6", surface: "#f8fafc", border: "#cbd5e1", text: "#172033", muted: "#475569" },
    layers: {
      conclusion: { node: "#5b21b6", plane: "#c4b5fd", edge: "#6d28d9" },
      event: { node: "#1d4ed8", plane: "#93c5fd", edge: "#1e40af" },
      evidence: { node: "#0f766e", plane: "#99f6e4", edge: "#0f766e" },
    },
    statuses: { conflict: "#b91c1c", stale: "#c2410c", confirmed: "#15803d", inference: "#475569", qualified: "#b45309" },
  } as const;
  ```

  Update `visualEncoding.ts` to use the shared node/edge values while keeping glyph, dashed-line, marker, and opacity logic unchanged. Export a helper for plane colors so `LayerPlane.tsx` does not maintain a second palette.

- [x] **Step 4: Run focused tests and verify they pass**

  Run `cd frontend && npm run test -- provenancePalette.test.ts visualEncoding.test.ts --run`.

  Expected: PASS, with tests proving layer colors are distinct and node/edge status semantics are retained.

- [x] **Step 5: Commit**

  ```bash
  git add frontend/src/components/provenance/provenancePalette.ts frontend/src/components/provenance/provenancePalette.test.ts frontend/src/components/provenance/visualEncoding.ts frontend/src/components/provenance/visualEncoding.test.ts
  git commit -m "feat: add high contrast provenance palette"
  ```

### Task 2: Apply the palette to the 3D scene and readable labels

**Files:**
- Modify: `frontend/src/components/provenance/LayerPlane.tsx`
- Modify: `frontend/src/components/provenance/ProvenanceScene.tsx`
- Modify: `frontend/src/components/provenance/InstancedNodes.tsx`
- Modify: `frontend/src/components/provenance/LabelLayer.tsx`
- Modify: `frontend/src/components/provenance/SpatialLayerCanvas3D.test.tsx`
- Modify: `frontend/src/components/provenance/ProvenanceGraphPage.test.tsx`

- [x] **Step 1: Add failing scene assertions**

  Extend the component tests to assert that the scene renders the light-analysis background and that the accessibility label remains present for the 3D canvas. Add a unit assertion for the label class contract (`provenance-node-label`) so the CSS change cannot silently remove readable labels.

- [x] **Step 2: Run the focused tests and verify the new assertions fail**

  Run `cd frontend && npm run test -- SpatialLayerCanvas3D.test.tsx ProvenanceGraphPage.test.tsx --run`.

  Expected: FAIL on the new palette/background assertions because the scene still uses `#07111f` and the old dark text treatment.

- [x] **Step 3: Implement scene-level contrast changes**

  Use the shared palette in `LayerPlane` and `ProvenanceScene`. Change the Three.js clear color and fog color to the pale stage background, increase plane opacity only enough to preserve layer silhouettes, and use dark layer labels with a white translucent backing. Keep camera, layout, particle, hit-target, and selection behavior intact.

- [x] **Step 4: Implement readable node labels without increasing node count**

  Keep instanced node geometry and hit targets unchanged. Update the HTML label styling hooks so labels use the light-card treatment, and preserve the existing max-label and selected-node logic.

- [x] **Step 5: Run focused tests and verify they pass**

  Run `cd frontend && npm run test -- SpatialLayerCanvas3D.test.tsx ProvenanceGraphPage.test.tsx --run`.

  Expected: PASS.

- [x] **Step 6: Commit**

  ```bash
  git add frontend/src/components/provenance/LayerPlane.tsx frontend/src/components/provenance/ProvenanceScene.tsx frontend/src/components/provenance/InstancedNodes.tsx frontend/src/components/provenance/LabelLayer.tsx frontend/src/components/provenance/SpatialLayerCanvas3D.test.tsx frontend/src/pages/ProvenanceGraphPage.test.tsx
  git commit -m "feat: apply high contrast colors to provenance scene"
  ```

### Task 3: Restyle the canvas shell, controls, and fallback view

**Files:**
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/components/provenance/ProvenanceFallbackView.test.tsx`
- Modify: `frontend/src/components/provenance/EvidenceAuditDrawer.test.tsx`

- [x] **Step 1: Add failing CSS contract checks**

  Add tests that render the fallback/drawer controls and assert the existing semantic class names remain present. Add a small source-level palette test that reads the CSS text and verifies the stage background, dark text, and light-card selectors are present; this guards against accidentally changing only the WebGL scene while leaving the surrounding controls low contrast.

- [x] **Step 2: Run focused tests and verify failure**

  Run `cd frontend && npm run test -- ProvenanceFallbackView.test.tsx EvidenceAuditDrawer.test.tsx --run`.

  Expected: FAIL on the new light-analysis CSS contract assertions.

- [x] **Step 3: Update CSS for the light-analysis direction**

  Restyle `.provenance-stage`, `.provenance-stage__toolbar`, `.provenance-legend`, `.provenance-layer-label`, `.provenance-node-label`, banners, empty/error states, fallback sections, and audit drawer with the palette. Use dark text on pale surfaces, visible borders, and shadows that separate cards from the canvas. Preserve focus rings, responsive breakpoints, and status swatch semantics.

- [x] **Step 4: Run focused tests and verify they pass**

  Run `cd frontend && npm run test -- ProvenanceFallbackView.test.tsx EvidenceAuditDrawer.test.tsx --run`.

  Expected: PASS.

- [x] **Step 5: Commit**

  ```bash
  git add frontend/src/styles.css frontend/src/components/provenance/ProvenanceFallbackView.test.tsx frontend/src/components/provenance/EvidenceAuditDrawer.test.tsx
  git commit -m "style: improve provenance contrast and controls"
  ```

### Task 4: Full verification and deployment

**Files:**
- Modify: `docs/superpowers/specs/2026-09-03-provenance-contrast-design.md` (checklist updates only)
- Modify: `docs/superpowers/plans/2026-09-03-provenance-contrast.md` (checklist updates only)

- [x] **Step 1: Run the complete frontend verification suite**

  Run `cd frontend && npm run lint && npm run test -- --run && npm run build && npm run test:e2e`.

  Expected: lint, all Vitest tests, production build, and the four real-browser provenance E2E tests pass. Existing chunk-size and React act warnings are acceptable if exit codes remain zero.

- [x] **Step 2: Inspect the built page locally**

  Start the frontend preview or use the existing dev server, open `/provenance`, and verify that the three planes, labels, controls, and legend are readable at the default viewport. Verify reduced-motion and fallback modes still render.

- [x] **Step 3: Commit documentation checklist updates**

  ```bash
  git add docs/superpowers/specs/2026-09-03-provenance-contrast-design.md docs/superpowers/plans/2026-09-03-provenance-contrast.md
  git commit -m "docs: record provenance contrast verification"
  ```

- [x] **Step 4: Deploy the merged result**

  Sync the repository to `yi5an@123.57.165.38:/home/yi5an/knowpilot/` using the existing exclusions for `.env`, databases, virtualenvs, `node_modules`, and local storage. Run `docker compose -f docker-compose.prod.yml up -d --build backend frontend` on the server.

- [x] **Step 5: Verify deployment**

### Implementation notes

The existing component test harness mocks the WebGL canvas, so the scene-level checks remain covered by the shared palette tests plus the existing canvas/page accessibility assertions. No runtime CSS parser is configured; the light-card contract is validated by the focused fallback and audit component suites and by the production build.

  Run `curl -fsS http://123.57.165.38:13080/api/v1/health` and refresh `/provenance` in the remote browser. Confirm the page is served from the new build and the light-analysis palette is visible.
