import { describe, expect, it } from "vitest";

import { parseCommand } from "./cli.js";

describe("collector CLI", () => {
  it.each([
    [["node", "cli.js", "run"], "run"],
    [["node", "cli.js", "login"], "login"],
    [["node", "cli.js", "status"], "status"],
    [["node", "cli.js", "install"], "install"],
    [["node", "cli.js", "uninstall"], "uninstall"],
  ] as const)("parses %s", (argv, command) => {
    expect(parseCommand([...argv])).toEqual({command});
  });

  it("rejects unsupported commands", () => {
    expect(() => parseCommand(["node", "cli.js", "unknown"])).toThrow("Unknown command");
  });
});
