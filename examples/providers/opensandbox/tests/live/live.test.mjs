// Live tier: the plugin over EPP against a real OpenSandbox server. Opt in with OPENSANDBOX_LIVE=1.
//
//   cd python-sdk/e2e/opensandbox && ./local-up.sh up && eval "$(./local-up.sh env)"
//   cd ../../examples/providers/opensandbox && OPENSANDBOX_LIVE=1 node tests/run.mjs live
//
// Reads EBX_OPENSANDBOX_BASE_URL / EBX_OPENSANDBOX_API_KEY (or the OPENSANDBOX_* names printed by local-up.sh env).
import test from "node:test";
import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { EppHost } from "../epp-client.mjs";

const live = process.env.OPENSANDBOX_LIVE === "1";
const baseUrl = process.env.EBX_OPENSANDBOX_BASE_URL ?? process.env.OPENSANDBOX_BASE_URL ?? "http://127.0.0.1:8080";
const apiKey = process.env.EBX_OPENSANDBOX_API_KEY ?? process.env.OPENSANDBOX_API_KEY;
const image = process.env.OPENSANDBOX_TEST_IMAGE ?? "python:3.12-slim";

const rpcError = async (promise) => {
  try {
    await promise;
  } catch (err) {
    return err.rpc;
  }
  assert.fail("expected an RPC error");
};

test("live: full lifecycle, exec, files, ports against a real OpenSandbox", { skip: !live, timeout: 240_000 }, async () => {
  const host = new EppHost();
  await host.initialize({ base_url: baseUrl, api_key: apiKey, default_image: image }, { http_timeout: 30, max_retries: 2 });
  let id;
  const call = (method, params = {}) => host.call(method, { sandbox_id: id, ...params });
  try {
    const rec = await host.call("sandbox.create", { template: "base", timeout: 300, metadata: { name: "ebx-live", suite: "node" }, envs: { LIVE_VAR: "bar" }, cpu: 1, memory: 512 });
    id = rec.sandbox_id;
    assert.equal(rec.status, "running");
    assert.equal(rec.template, image);

    // exec
    const r = await call("exec.run", { cmd: "sh", args: ["-c", "echo out; echo err >&2; echo $LIVE_VAR; printf 'x\\r\\ny'; exit 3"], timeout: 30 });
    assert.deepEqual(r, { exit_code: 3, stdout: "out\nbar\nx\r\ny", stderr: "err\n" });
    assert.equal((await call("exec.run", { cmd: "nonexistent-xyz", args: [], timeout: 30 })).exit_code, 127);
    assert.equal((await call("exec.run", { cmd: "cat", args: [], stdin: "piped", timeout: 30 })).stdout, "piped");
    assert.equal((await call("exec.run", { cmd: "id", args: ["-un"], user: "nobody", timeout: 30 })).stdout, "nobody\n");
    assert.equal((await rpcError(call("exec.run", { cmd: "sleep", args: ["10"], timeout: 1 }))).code, -32005);

    const started = await call("exec.start", { cmd: "sh", args: ["-c", "echo a; sleep 0.5; echo b >&2; exit 2"], timeout: 30 });
    const exit = await host.waitNote((n) => n.method === "exec.exit" && n.params.process_id === started.process_id);
    assert.equal(exit.params.exit_code, 2);
    const streamed = host.notes.filter((n) => n.method === "exec.output" && n.params.process_id === started.process_id).map((n) => `${n.params.stream}:${n.params.data}`);
    assert.deepEqual(streamed, ["stdout:a\n", "stderr:b\n"]);

    // processes
    const bg = await call("exec.start", { cmd: "sleep", args: ["60"], timeout: 120, detached: true });
    const { processes } = await call("process.list");
    const sleeper = processes.find((p) => p.command.startsWith("sleep 60"));
    assert.ok(sleeper, JSON.stringify(processes));
    await call("process.kill", { pid: sleeper.pid });
    await host.waitNote((n) => n.method === "exec.exit" && n.params.process_id === bg.process_id);
    assert.equal((await rpcError(call("process.stdin", { pid: 1, data: "x" }))).code, -32003);

    // files: 3 MB of random bytes survive base64 + multipart + download
    const blob = randomBytes(3 * 1024 * 1024);
    await call("files.write", { path: "/tmp/live/blob.bin", content_b64: blob.toString("base64") });
    const back = await call("files.read", { path: "/tmp/live/blob.bin" });
    assert.ok(Buffer.from(back.content_b64, "base64").equals(blob));
    const part = await call("files.read", { path: "/tmp/live/blob.bin", offset: 10, length: 20 });
    assert.ok(Buffer.from(part.content_b64, "base64").equals(blob.subarray(10, 30)));
    await call("files.write", { path: "/tmp/live/sub/hello.txt", content_b64: Buffer.from("hello\n").toString("base64"), mode: 0o640 });
    assert.equal((await call("files.stat", { path: "/tmp/live/sub/hello.txt" })).mode, 640);
    assert.deepEqual((await call("files.list", { path: "/tmp/live" })).entries.map((e) => e.name).sort(), ["blob.bin", "sub"]);
    assert.deepEqual((await call("files.search", { path: "/tmp/live", pattern: "**/*.txt" })).entries.map((e) => e.path), ["/tmp/live/sub/hello.txt"]);
    await call("files.move", { source: "/tmp/live/sub/hello.txt", destination: "/tmp/live/moved.txt" });
    assert.equal((await rpcError(call("files.stat", { path: "/tmp/live/sub/hello.txt" }))).data.sdk_code, "E4001");
    assert.equal((await rpcError(call("files.move", { source: "/tmp/live/moved.txt", destination: "/tmp/live/blob.bin" }))).code, -32006);
    await call("files.remove", { path: "/tmp/live/moved.txt" });
    await call("files.remove", { path: "/tmp/live" });
    assert.equal((await rpcError(call("files.read", { path: "/tmp/live" }))).code, -32002);

    // lifecycle
    assert.equal((await host.call("sandbox.list", { metadata: { suite: "node" }, status: "running" })).sandboxes.some((s) => s.sandbox_id === id), true);
    const ttl = await call("sandbox.set_timeout", { timeout: 900 });
    const delta = Date.parse(ttl.expires_at) - Date.now();
    assert.ok(Math.abs(delta - 900_000) < 5000, `ttl off by ${delta - 900_000} ms`);
    await call("sandbox.pause");
    assert.equal((await call("sandbox.get")).status, "paused");
    await call("sandbox.resume");
    assert.equal((await call("exec.run", { cmd: "echo", args: ["alive"], timeout: 30 })).stdout, "alive\n");

    // ports
    const url = await call("ports.url", { port: 8000 });
    assert.match(url.url, /^http:\/\/.+\/proxy\/8000$/);
    const served = await call("exec.start", { cmd: "python3", args: ["-m", "http.server", "8000", "--directory", "/etc"], timeout: 60, detached: true });
    await new Promise((r) => setTimeout(r, 1500));
    const page = await fetch(`${url.url}/hostname`, { headers: url.headers ?? {} });
    assert.equal(page.status, 200);
    await call("process.kill", { pid: served.process_id });

    // errors
    assert.equal((await rpcError(host.call("sandbox.create", { template: "this-image-does-not-exist.invalid/x:1" }))).code, -32002);
    assert.equal((await rpcError(host.call("sandbox.create", { template: "base", metadata: { "bad key": "v" } }))).code, -32006);
    assert.equal((await rpcError(host.call("sandbox.create", { template: "base", disk: 10 }))).code, -32006);
  } finally {
    if (id) {
      await host.call("sandbox.kill", { sandbox_id: id });
      assert.deepEqual(await host.call("sandbox.kill", { sandbox_id: id }), {}, "second kill is idempotent");
      assert.equal((await rpcError(host.call("sandbox.get", { sandbox_id: id }))).code, -32002);
    }
    await host.close();
  }
});

test("live: a wrong API key is -32001", { skip: !live }, async () => {
  const host = new EppHost();
  await host.initialize({ base_url: baseUrl, api_key: "definitely-wrong-key" });
  const err = await rpcError(host.call("sandbox.list", {}));
  assert.equal(err.code, -32001);
  assert.ok(!JSON.stringify(err).includes("definitely-wrong-key"));
  await host.close();
});
