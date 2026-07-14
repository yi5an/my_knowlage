export interface DiscoveredOperation {
  queryId: string;
  protocol: "legacy" | "relay";
  featureSwitches: string[];
  fieldToggles: string[];
}

export type OperationMap = Record<string, DiscoveredOperation>;

export class QueryChangedError extends Error {
  readonly code = "query_changed";

  constructor(operationName: string) {
    super(`X Web operation changed or disappeared: ${operationName}`);
    this.name = "QueryChangedError";
  }
}

export function discoverOperations(source: string, names: string[]): OperationMap {
  const operations: OperationMap = {};
  for (const name of names) {
    const operation = discoverOperation(source, name);
    if (!operation) throw new QueryChangedError(name);
    operations[name] = operation;
  }
  return operations;
}

export function discoverOperationsFromBundles(sources: string[], names: string[]): OperationMap {
  const operations: OperationMap = {};
  for (const name of names) {
    const operation = sources.map((source) => discoverOperation(source, name)).find(Boolean);
    if (!operation) throw new QueryChangedError(name);
    operations[name] = operation;
  }
  return operations;
}

function discoverOperation(source: string, name: string): DiscoveredOperation | undefined {
  const relayPattern = new RegExp(
    "params:\\{id:`([^`]+)`[\\s\\S]{0,500}?name:`" + escapeRegex(name) + "`",
  );
  const relayMatch = source.match(relayPattern);
  if (relayMatch?.[1]) {
    return {
      queryId: relayMatch[1],
      protocol: "relay",
      featureSwitches: [],
      fieldToggles: [],
    };
  }

    const marker = `operationName:"${name}"`;
    const offset = source.indexOf(marker);
    if (offset < 0) return undefined;

    const before = source.slice(Math.max(0, offset - 2_000), offset);
    const queryMatches = [...before.matchAll(/queryId:"([^"]+)"/g)];
    const queryId = queryMatches.at(-1)?.[1];
    if (!queryId) return undefined;

    const metadata = source.slice(offset, offset + 12_000);
    return {
      queryId,
      protocol: "legacy",
      featureSwitches: parseStringArray(metadata, "featureSwitches"),
      fieldToggles: parseStringArray(metadata, "fieldToggles"),
    };
}

function parseStringArray(source: string, key: string): string[] {
  const match = source.match(new RegExp(`${key}:\\[([^\\]]*)\\]`));
  if (!match?.[1]) return [];
  return [...match[1].matchAll(/"([^"]+)"/g)].map((item) => item[1]).filter(Boolean) as string[];
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
