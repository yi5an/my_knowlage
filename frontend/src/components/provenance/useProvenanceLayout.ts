import { useEffect, useState } from "react";

import type { ProvenanceGraphResponse } from "../../types/provenance";
import {
  computeProvenanceLayout,
  positionsFromEntries,
  type ProvenancePosition,
} from "./layout";

export interface ProvenanceLayoutAdapter {
  compute(
    graph: ProvenanceGraphResponse,
    serializedFilters: string,
  ): Promise<Map<string, ProvenancePosition>>;
  terminate(): void;
}

export type ProvenanceLayoutAdapterFactory = () => ProvenanceLayoutAdapter;

export class SynchronousLayoutAdapter implements ProvenanceLayoutAdapter {
  async compute(
    graph: ProvenanceGraphResponse,
    serializedFilters: string,
  ): Promise<Map<string, ProvenancePosition>> {
    return computeProvenanceLayout(graph, serializedFilters);
  }

  terminate(): void {}
}

class BrowserWorkerLayoutAdapter implements ProvenanceLayoutAdapter {
  private worker = new Worker(new URL("./layout.worker.ts", import.meta.url), {
    type: "module",
  });

  compute(
    graph: ProvenanceGraphResponse,
    serializedFilters: string,
  ): Promise<Map<string, ProvenancePosition>> {
    return new Promise((resolve, reject) => {
      this.worker.onmessage = (event: MessageEvent<Array<[string, ProvenancePosition]>>) => {
        resolve(positionsFromEntries(event.data));
      };
      this.worker.onerror = () => reject(new Error("Provenance layout worker failed"));
      this.worker.postMessage({ graph, serializedFilters });
    });
  }

  terminate(): void {
    this.worker.terminate();
  }
}

const defaultAdapterFactory: ProvenanceLayoutAdapterFactory = () => {
  if (typeof Worker === "undefined") return new SynchronousLayoutAdapter();
  return new BrowserWorkerLayoutAdapter();
};

export function useProvenanceLayout(
  graph: ProvenanceGraphResponse,
  serializedFilters: string,
  adapterFactory: ProvenanceLayoutAdapterFactory = defaultAdapterFactory,
): Map<string, ProvenancePosition> {
  const [positions, setPositions] = useState(() =>
    computeProvenanceLayout(graph, serializedFilters),
  );

  useEffect(() => {
    let active = true;
    const adapter = adapterFactory();
    void adapter
      .compute(graph, serializedFilters)
      .then((next) => {
        if (active) setPositions(next);
      })
      .catch(() => {
        if (active) setPositions(computeProvenanceLayout(graph, serializedFilters));
      });
    return () => {
      active = false;
      adapter.terminate();
    };
  }, [adapterFactory, graph, serializedFilters]);

  return positions;
}
