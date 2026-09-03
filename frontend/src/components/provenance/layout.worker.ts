/// <reference lib="webworker" />

import type { ProvenanceGraphResponse } from "../../types/provenance";
import { computeProvenanceLayout } from "./layout";

export interface LayoutWorkerRequest {
  graph: ProvenanceGraphResponse;
  serializedFilters: string;
}

self.onmessage = (event: MessageEvent<LayoutWorkerRequest>) => {
  const { graph, serializedFilters } = event.data;
  const positions = computeProvenanceLayout(graph, serializedFilters);
  self.postMessage([...positions.entries()]);
};

export {};
