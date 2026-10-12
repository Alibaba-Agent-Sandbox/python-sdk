// Runs the Node test suites (no glob support needed, works on Node 20+ and on Windows).
// Usage: node tests/run.mjs [unit|mock|live ...]   (default: unit mock)
import { readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const suites = process.argv.length > 2 ? process.argv.slice(2) : ["unit", "mock"];
const files = suites.flatMap((s) => readdirSync(join(here, s)).filter((f) => f.endsWith(".test.mjs")).map((f) => join(here, s, f)));
const res = spawnSync(process.execPath, ["--test", "--test-concurrency=1", ...files], { stdio: "inherit" });
process.exit(res.status ?? 1);
