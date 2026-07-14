import { describe, expect, it } from "vitest";

import { loadConfig, renderLaunchAgent } from "./config.js";

describe("collector config", () => {
  it("uses a stable user-data layout and environment overrides", () => {
    const config = loadConfig(
      {
        KNOWPILOT_URL: "http://127.0.0.1:8010/",
        X_COLLECTOR_ID: "mac-test",
        X_COLLECTOR_DATA_DIR: "/tmp/x-collector-test",
        X_COLLECTOR_TOKEN: "secret-token",
      },
      "/Users/test",
    );

    expect(config).toMatchObject({
      backendUrl: "http://127.0.0.1:8010",
      collectorId: "mac-test",
      dataDir: "/tmp/x-collector-test",
      profileDir: "/tmp/x-collector-test/browser-profile",
      spoolDir: "/tmp/x-collector-test/spool",
      token: "secret-token",
    });
  });

  it("renders a LaunchAgent without placing secrets in the plist", () => {
    const plist = renderLaunchAgent({
      nodePath: "/opt/homebrew/bin/node",
      appPath: "/repo/tools/x-collector/dist/cli.js",
      envFile: "/Users/test/Library/Application Support/KnowPilot/x-collector/.env",
      logDir: "/Users/test/Library/Logs/KnowPilot",
    });

    expect(plist).toContain("com.knowpilot.x-collector");
    expect(plist).toContain("/opt/homebrew/bin/node");
    expect(plist).toContain("/repo/tools/x-collector/dist/cli.js");
    expect(plist).toContain("X_COLLECTOR_ENV_FILE");
    expect(plist).not.toContain("secret-token");
  });
});
