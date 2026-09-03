import { expect, test, type Page } from "@playwright/test";

import { edgeDetail, provenanceGraph } from "./fixtures/provenanceGraphs";

type DebugSnapshot = {
  renderer: string;
  frame: number;
  cameraPosition: [number, number, number];
  cameraQuaternion: [number, number, number, number];
  controlsTarget: [number, number, number];
  selectedNodeId: string | null;
  geometries: number;
  textures: number;
  mounted: boolean;
  reducedMotion: boolean;
  selectedEdgeCount: number;
  nodeScreenPositions: Record<string, [number, number]>;
  edgeScreenPositions: Record<string, [number, number]>;
};

async function mockGraph(page: Page, size: 100 | 500 | 2000) {
  const graph = provenanceGraph(size);
  await page.route("**/api/v1/provenance/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/overview") || url.pathname.includes("/nodes/")) {
      await route.fulfill({ json: graph });
      return;
    }
    const edgeMatch = url.pathname.match(/\/edges\/([^/]+)$/);
    if (edgeMatch) {
      const edgeId = decodeURIComponent(edgeMatch[1]);
      const edge = graph.edges.find((item) => item.id === edgeId) ?? graph.edges[0];
      await route.fulfill({ json: edgeDetail(edge) });
      return;
    }
    if (url.pathname.includes("/review")) {
      await route.fulfill({ json: { edge: graph.edges[0], previous_review_status: "pending_review", reviewed_at: new Date().toISOString() } });
      return;
    }
    await route.fulfill({ status: 404, json: { error: { message: "fixture route not found" } } });
  });
  return graph;
}

async function debugSnapshot(page: Page): Promise<DebugSnapshot> {
  return page.evaluate(() => (window as unknown as { __KNOWPILOT_PROVENANCE_DEBUG__: DebugSnapshot }).__KNOWPILOT_PROVENANCE_DEBUG__);
}

function distanceToTarget(snapshot: DebugSnapshot): number {
  return Math.hypot(
    snapshot.cameraPosition[0] - snapshot.controlsTarget[0],
    snapshot.cameraPosition[1] - snapshot.controlsTarget[1],
    snapshot.cameraPosition[2] - snapshot.controlsTarget[2],
  );
}

async function dragCanvas(page: Page, button: "left" | "right" | "middle", dx: number, dy: number) {
  const canvas = page.locator("[data-provenance-canvas] canvas");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas is not visible");
  const start = { x: box.x + box.width * 0.55, y: box.y + box.height * 0.55 };
  await page.mouse.move(start.x, start.y);
  await page.mouse.down({ button });
  await page.mouse.move(start.x + dx, start.y + dy, { steps: 8 });
  await page.mouse.up({ button });
  await page.waitForTimeout(250);
}

test("rotates, pans, zooms, raycasts, and resets in a real WebGL renderer", async ({ page }) => {
  await mockGraph(page, 100);
  await page.goto("/provenance?fixture=100");
  await expect(page.locator('[data-webgl-ready="true"]')).toBeVisible();
  await page.locator("[data-provenance-canvas]").focus();
  await page.keyboard.press("Escape");
  await page.waitForFunction(
    () =>
      ((window as unknown as { __KNOWPILOT_PROVENANCE_DEBUG__?: { frame: number } })
        .__KNOWPILOT_PROVENANCE_DEBUG__?.frame ?? 0) >= 1,
  );
  const initial = await debugSnapshot(page);
  expect(initial.renderer).toBe("WebGLRenderer");
  expect(initial.geometries).toBeGreaterThan(0);

  await dragCanvas(page, "left", 120, 30);
  expect((await debugSnapshot(page)).cameraQuaternion).not.toEqual(initial.cameraQuaternion);

  const beforeRightPan = await debugSnapshot(page);
  await dragCanvas(page, "right", 80, 0);
  expect((await debugSnapshot(page)).controlsTarget).not.toEqual(beforeRightPan.controlsTarget);

  const beforeMiddlePan = await debugSnapshot(page);
  await dragCanvas(page, "middle", -60, 15);
  expect((await debugSnapshot(page)).controlsTarget).not.toEqual(beforeMiddlePan.controlsTarget);

  const beforeShiftPan = await debugSnapshot(page);
  await page.keyboard.down("Shift");
  await dragCanvas(page, "left", 55, 0);
  await page.keyboard.up("Shift");
  expect((await debugSnapshot(page)).controlsTarget).not.toEqual(beforeShiftPan.controlsTarget);

  const beforeZoom = await debugSnapshot(page);
  await page.locator("[data-provenance-canvas] canvas").hover();
  await page.mouse.wheel(0, -480);
  await page.waitForTimeout(250);
  expect(distanceToTarget(await debugSnapshot(page))).toBeLessThan(distanceToTarget(beforeZoom));

  const nodePoint = (await debugSnapshot(page)).nodeScreenPositions["event-1"];
  await page.mouse.click(nodePoint[0], nodePoint[1]);
  await expect(page).toHaveURL(/node=event-1/);
  await expect.poll(async () => (await debugSnapshot(page)).selectedNodeId).toBe("event-1");

  const edgePoint = (await debugSnapshot(page)).edgeScreenPositions["edge-event-conclusion-0"];
  await page.mouse.click(edgePoint[0], edgePoint[1]);
  await expect(page.locator('[aria-label="关系审计"]')).toBeVisible();

  const wrapper = page.locator("[data-provenance-canvas]");
  await wrapper.focus();
  const beforeKeyboard = await debugSnapshot(page);
  await page.keyboard.press("ArrowRight");
  expect((await debugSnapshot(page)).controlsTarget).not.toEqual(beforeKeyboard.controlsTarget);
  const beforeKeyboardZoom = await debugSnapshot(page);
  await page.keyboard.press("+");
  expect(distanceToTarget(await debugSnapshot(page))).toBeLessThan(
    distanceToTarget(beforeKeyboardZoom),
  );
  await page.keyboard.press("-");
  await page.keyboard.press("Escape");
  await page.keyboard.press("r");

  const canvasBox = await page.locator("[data-provenance-canvas] canvas").boundingBox();
  if (!canvasBox) throw new Error("canvas is not visible");
  await page.mouse.dblclick(canvasBox.x + 24, canvasBox.y + canvasBox.height - 32);
  await expect.poll(async () => distanceToTarget(await debugSnapshot(page))).toBeCloseTo(distanceToTarget(initial), 1);

  await page.getByRole("link", { name: /KnowPilot/ }).click();
  await expect(page).toHaveURL("/");
  await expect.poll(async () => (await debugSnapshot(page)).mounted).toBe(false);
  const unmounted = await debugSnapshot(page);
  expect(unmounted.geometries).toBe(0);
  expect(unmounted.textures).toBe(0);
});

test("honors reduced motion and shows an explicit no-WebGL fallback", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockGraph(page, 100);
  await page.goto("/provenance?fixture=100");
  await expect(page.locator('[data-webgl-ready="true"]')).toBeVisible();
  expect((await debugSnapshot(page)).reducedMotion).toBe(true);

  const noWebglPage = await page.context().newPage();
  await noWebglPage.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type: string, ...args: unknown[]) {
      if (type === "webgl" || type === "webgl2") return null;
      return original.call(this, type, ...args as []);
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
  await mockGraph(noWebglPage, 100);
  await noWebglPage.goto("/provenance?fixture=100");
  await expect(noWebglPage.getByText("WebGL 不可用")).toBeVisible();
  await noWebglPage.close();
});

test("preserves the selected path under the 2000-node quality tier", async ({ page }) => {
  const graph = await mockGraph(page, 2000);
  await page.goto("/provenance?fixture=2000&node=event-1");
  await expect(page.locator('[data-webgl-ready="true"]')).toBeVisible();
  await expect.poll(async () => (await debugSnapshot(page)).selectedEdgeCount).toBe(graph.edges.length);
});
