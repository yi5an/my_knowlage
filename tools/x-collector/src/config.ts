import { homedir, hostname } from "node:os";
import { join } from "node:path";

export interface CollectorConfig {
  backendUrl: string;
  token?: string;
  collectorId: string;
  version: string;
  dataDir: string;
  profileDir: string;
  spoolDir: string;
  maxSpoolBytes: number;
  pollIntervalMs: number;
  headless: boolean;
}

export interface LaunchAgentOptions {
  nodePath: string;
  appPath: string;
  envFile: string;
  logDir: string;
}

export function loadConfig(
  env: Record<string, string | undefined> = process.env,
  homeDir: string = homedir(),
): CollectorConfig {
  const dataDir =
    env.X_COLLECTOR_DATA_DIR ||
    join(homeDir, "Library/Application Support/KnowPilot/x-collector");
  return {
    backendUrl: (env.KNOWPILOT_URL || "http://127.0.0.1:8010").replace(/\/$/, ""),
    token: env.X_COLLECTOR_TOKEN,
    collectorId: env.X_COLLECTOR_ID || hostname(),
    version: env.X_COLLECTOR_VERSION || "0.1.0",
    dataDir,
    profileDir: join(dataDir, "browser-profile"),
    spoolDir: join(dataDir, "spool"),
    maxSpoolBytes: Number(env.X_COLLECTOR_MAX_SPOOL_BYTES || 50 * 1024 * 1024),
    pollIntervalMs: Number(env.X_COLLECTOR_POLL_INTERVAL_MS || 60_000),
    // X started rejecting headless Chromium with 403 around 2026-07-17
    // (blank page, guest activation never fires). Headful is the default;
    // set X_COLLECTOR_HEADLESS=1 only on hosts where headless still works.
    headless: ["1", "true"].includes(String(env.X_COLLECTOR_HEADLESS ?? "").toLowerCase()),
  };
}

export function renderLaunchAgent(options: LaunchAgentOptions): string {
  const xml = (value: string): string =>
    value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  const workingDirectory = options.appPath.replace(/\/[^/]+$/, "");
  const lines = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
    '<plist version="1.0">',
    "<dict>",
    "  <key>Label</key><string>com.knowpilot.x-collector</string>",
    "  <key>ProgramArguments</key>",
    "  <array>",
    `    <string>${xml(options.nodePath)}</string>`,
    `    <string>${xml(options.appPath)}</string>`,
    "    <string>run</string>",
    "  </array>",
    "  <key>EnvironmentVariables</key>",
    `  <dict><key>X_COLLECTOR_ENV_FILE</key><string>${xml(options.envFile)}</string></dict>`,
    `  <key>WorkingDirectory</key><string>${xml(workingDirectory)}</string>`,
    "  <key>RunAtLoad</key><true/>",
    "  <key>KeepAlive</key><true/>",
    `  <key>StandardOutPath</key><string>${xml(join(options.logDir, "x-collector.log"))}</string>`,
    `  <key>StandardErrorPath</key><string>${xml(join(options.logDir, "x-collector.error.log"))}</string>`,
    "</dict>",
    "</plist>",
  ];
  return lines.join("\n") + "\n";
}
