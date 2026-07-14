import { mkdir, readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline/promises";

import { BackendClient } from "./backend-client.js";
import { loadConfig, renderLaunchAgent } from "./config.js";
import { PlaywrightKeywordSearchSession } from "./session.js";

const ALLOWED_COMMANDS = new Set(["run", "once", "login", "status", "install", "uninstall"]);

export function parseCommand(argv: string[]): {command: string} {
  const command = argv[2] || "status";
  if (!ALLOWED_COMMANDS.has(command)) throw new Error(`Unknown command: ${command}`);
  return {command};
}

export async function main(argv: string[] = process.argv): Promise<void> {
  const {command} = parseCommand(argv);
  const config = loadConfig(await loadEnvFile(process.env.X_COLLECTOR_ENV_FILE));

  switch (command) {
    case "status":
      console.log(JSON.stringify({collector_id: config.collectorId, data_dir: config.dataDir}));
      return;
    case "login":
      await login(config.profileDir);
      return;
    case "install":
      await install(config);
      return;
    case "uninstall":
      await uninstall();
      return;
    case "once":
    case "run": {
      const {runLoop} = await import("./runtime.js");
      await runLoop(config, command === "once");
      return;
    }
  }
}

async function login(profileDir: string): Promise<void> {
  const session = await PlaywrightKeywordSearchSession.open(profileDir, {headless: false});
  try {
    console.log("请在打开的 X 浏览器窗口完成登录，完成后回到终端按回车继续。");
    const readline = createInterface({input: process.stdin, output: process.stdout});
    await readline.question("");
    readline.close();
    console.log(JSON.stringify({login_status: await session.loginStatus()}));
  } finally {
    await session.close();
  }
}

async function install(config: ReturnType<typeof loadConfig>): Promise<void> {
  const launchAgentsDir = join(homedir(), "Library/LaunchAgents");
  const logDir = join(homedir(), "Library/Logs/KnowPilot");
  const envFile = join(config.dataDir, ".env");
  await mkdir(config.dataDir, {recursive: true, mode: 0o700});
  await mkdir(logDir, {recursive: true});
  await writeFile(
    join(config.dataDir, ".env.example"),
    "KNOWPILOT_URL=http://127.0.0.1:8010\nX_COLLECTOR_ID=\nX_COLLECTOR_TOKEN=\n",
    {mode: 0o600},
  );
  await mkdir(launchAgentsDir, {recursive: true});
  const plist = renderLaunchAgent({
    nodePath: process.execPath,
    appPath: join(process.cwd(), "dist/cli.js"),
    envFile,
    logDir,
  });
  await writeFile(join(launchAgentsDir, "com.knowpilot.x-collector.plist"), plist, {mode: 0o600});
  console.log(`LaunchAgent 已写入 ${launchAgentsDir}`);
}

async function uninstall(): Promise<void> {
  const path = join(homedir(), "Library/LaunchAgents/com.knowpilot.x-collector.plist");
  await readFile(path).then(() => writeFile(path, "", {mode: 0o600})).catch(() => undefined);
  console.log(`LaunchAgent 已停用：${path}`);
}

async function loadEnvFile(path: string | undefined): Promise<Record<string, string | undefined>> {
  if (!path) return process.env;
  const values = {...process.env};
  const content = await readFile(path, "utf8").catch(() => "");
  for (const line of content.split("\n")) {
    const match = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (match?.[1]) values[match[1]] = match[2];
  }
  return values;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((error: unknown) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
