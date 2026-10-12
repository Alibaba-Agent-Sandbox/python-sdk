// Minimal EPP/1 host used by the tests: spawns the plugin exactly like a real host would.

import { spawn } from "node:child_process";
import { createInterface } from "node:readline";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const PLUGIN_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");

export class EppHost {
  constructor({ cwd = PLUGIN_DIR, env } = {}) {
    this.proc = spawn(process.execPath, [join(PLUGIN_DIR, "provider.mjs")], {
      cwd,
      env: env ?? { PATH: process.env.PATH },
      stdio: ["pipe", "pipe", "pipe"],
    });
    this.nextId = 0;
    this.pending = new Map();
    this.notes = [];
    this.waiters = [];
    this.stderr = "";
    this.proc.stderr.on("data", (d) => { this.stderr += d; });
    this.exited = new Promise((resolve) => this.proc.on("exit", (code) => resolve(code)));
    createInterface({ input: this.proc.stdout }).on("line", (line) => {
      const msg = JSON.parse(line);
      if (msg.id !== undefined && msg.id !== null && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(Object.assign(new Error(msg.error.message), { rpc: msg.error }));
        else resolve(msg.result);
      } else if (msg.method) {
        this.notes.push(msg);
        for (const w of this.waiters.slice()) w();
      }
    });
  }

  call(method, params = {}) {
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.proc.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
    });
  }

  raw(line) {
    this.proc.stdin.write(`${line}\n`);
  }

  /** Resolve once a notification matching `pred` has arrived (already-received ones count). */
  waitNote(pred, timeoutMs = 20_000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`timed out waiting for notification; got ${JSON.stringify(this.notes)}`)), timeoutMs);
      const check = () => {
        const hit = this.notes.find(pred);
        if (hit) {
          clearTimeout(timer);
          this.waiters = this.waiters.filter((w) => w !== check);
          resolve(hit);
          return true;
        }
        return false;
      };
      if (!check()) this.waiters.push(check);
    });
  }

  async initialize(config = {}, core = {}) {
    return this.call("initialize", {
      protocol: "epp/1",
      host: { name: "test-host", version: "0" },
      provider_id: "opensandbox",
      config,
      core,
      locale: "en",
      data_dir: process.cwd(),
    });
  }

  async close() {
    try {
      await this.call("shutdown");
    } catch {
      /* already gone */
    }
    this.proc.stdin.end();
    const timer = setTimeout(() => this.proc.kill("SIGKILL"), 3000);
    const code = await this.exited;
    clearTimeout(timer);
    return code;
  }
}
