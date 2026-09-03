import type { EvidenceAnchor } from "../../types/provenance";

function query(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined) params.set(key, String(value));
  });
  return params.toString();
}

function safeSourceUri(value: string | null): string | null {
  if (!value) return null;
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function evidenceLocatorHref(anchor: EvidenceAnchor): string | null {
  const documentId = anchor.document_id ? encodeURIComponent(anchor.document_id) : null;
  const locator = anchor.locator;
  if (locator.type === "text_span" && documentId) {
    return `/reader/${documentId}?${query({
      chunk: locator.chunk_id,
      start: locator.start_offset,
      end: locator.end_offset,
    })}`;
  }
  if (locator.type === "pdf_region" && documentId) {
    return `/reader/${documentId}?${query({
      page: locator.page_no,
      bbox: locator.bbox.join(","),
      chunk: locator.chunk_id ?? undefined,
    })}`;
  }
  if (locator.type === "media_segment" && documentId) {
    return `/youtube/summary/${documentId}?${query({
      start_ms: locator.start_ms,
      end_ms: locator.end_ms,
    })}`;
  }
  if (locator.type === "image_region" && documentId) {
    return `/documents/${documentId}/frames?${query({
      frame: locator.frame_id,
      bbox: locator.bbox.join(","),
    })}`;
  }
  if (locator.type === "web_fragment") return safeSourceUri(anchor.source_uri_snapshot);
  return null;
}

export function EvidenceLocatorLink({ anchor }: { anchor: EvidenceAnchor }) {
  const href = evidenceLocatorHref(anchor);
  const label = `定位原文：${anchor.quote}`;
  if (!href) return <span className="provenance-evidence__unavailable">原文定位不可用</span>;
  const external = href.startsWith("http");
  return (
    <a href={href} aria-label={label} target={external ? "_blank" : undefined} rel="noreferrer">
      定位原文
    </a>
  );
}
