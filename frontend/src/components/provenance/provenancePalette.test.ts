import { describe, expect, it } from "vitest";

import { PROVENANCE_PALETTE } from "./provenancePalette";

describe("PROVENANCE_PALETTE", () => {
  it("uses distinct dark node colors for the three semantic layers", () => {
    const colors = Object.values(PROVENANCE_PALETTE.layers).map((layer) => layer.node);
    expect(new Set(colors).size).toBe(3);
    colors.forEach((color) => expect(color).toMatch(/^#[0-9a-f]{6}$/i));
  });

  it("keeps plane colors distinct from their node colors", () => {
    Object.values(PROVENANCE_PALETTE.layers).forEach((layer) => {
      expect(layer.plane).not.toBe(layer.node);
      expect(layer.edge).not.toBe(layer.node);
    });
  });

  it("defines readable stage tokens and semantic status colors", () => {
    expect(PROVENANCE_PALETTE.stage.background).toBe("#eef2f6");
    expect(PROVENANCE_PALETTE.stage.text).toBe("#172033");
    expect(PROVENANCE_PALETTE.statuses.conflict).not.toBe(PROVENANCE_PALETTE.statuses.stale);
  });
});
