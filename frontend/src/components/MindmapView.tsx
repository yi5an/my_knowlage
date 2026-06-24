import { useEffect, useRef } from "react";
import { Transformer } from "markmap-lib";
import { Markmap } from "markmap-view";

import type { MindmapNode } from "../services/youtubeApi";

export interface MindmapViewProps {
  data: { root_title: string; children: MindmapNode[] };
}

/**
 * Convert the recursive MindmapNode tree into a markdown string that
 * markmap-lib can transform into a radial mindmap. Each nesting level maps
 * to a deeper markdown heading (# root, ## topic, ### subtopic, ...).
 *
 * Timestamps are embedded inline (e.g. "向量加法 [04:40]") so they're visible
 * in the rendered nodes without extra plumbing.
 */
function toMarkdown(node: MindmapNode, level: number): string {
  const heading = "#".repeat(Math.min(level, 6));
  // Embed the timestamp label into the node text when present.
  const ts = node.timestamp_str ? ` [${node.timestamp_str}]` : "";
  const ownLine = `${heading} ${node.title}${ts}`;
  const childLines = (node.children ?? []).map((c) => toMarkdown(c, level + 1));
  return [ownLine, ...childLines].join("\n");
}

function mindmapToMarkdown(data: MindmapViewProps["data"]): string {
  const rootLines = toMarkdown(
    { title: data.root_title, children: data.children, timestamp_str: null },
    1,
  );
  // markmap-lib expects markdown where the first # heading is the root node.
  // We already built that, so just return it as-is.
  return rootLines;
}

export function MindmapView({ data }: MindmapViewProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  // markmap-view's Markmap instance is stateful (it manages d3 under the hood).
  // Keep it in a ref so we re-render into the same instance on data changes
  // rather than stacking SVGs.
  const mmRef = useRef<Markmap | null>(null);

  useEffect(() => {
    if (!svgRef.current) return;

    const transformer = new Transformer();
    const markdown = mindmapToMarkdown(data);
    const { root } = transformer.transform(markdown);

    // Create the Markmap instance once, then re-use it for updates.
    if (!mmRef.current) {
      mmRef.current = Markmap.create(svgRef.current);
    }
    mmRef.current.setData(root);
    // Fit the diagram to the container after data settles. markmap's fit()
    // is async (it animates), so call it on the next frame to ensure the
    // new data has been laid out first.
    requestAnimationFrame(() => {
      mmRef.current?.fit();
    });
  }, [data]);

  // Clean up the instance on unmount to avoid d3 leaks.
  useEffect(() => {
    return () => {
      mmRef.current?.destroy();
      mmRef.current = null;
    };
  }, []);

  return (
    // markmap draws nodes at arbitrary SVG coordinates (radial layout), so
    // the diagram frequently extends beyond the viewport. Wrap the <svg> in
    // a scrollable div so the user can pan around without nodes getting
    // clipped by the Card's overflow:hidden. The svg itself is oversized to
    // give d3 room; the div clips + scrolls.
    <div
      style={{
        width: "100%",
        height: 600,
        overflow: "auto",
        // A subtle background so the scroll area reads as a distinct surface.
        background: "#fafafa",
        border: "1px solid #f0f0f0",
        borderRadius: 8,
      }}
    >
      <svg
        ref={svgRef}
        style={{ width: "100%", height: "100%", minHeight: 600 }}
      />
    </div>
  );
}
