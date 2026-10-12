// The whole plugin over real EPP (stdin/stdout) against the in-process mock OpenSandbox.
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { startMock } from "./mock-opensandbox.mjs";
import { EppHost } from "../epp-client.mjs";

const b64 = (s) => Buffer.from(s, "latin1").toString("base64");

async function withPlugin(mockOptions, config, fn) {
  const mock = await startMock(mockOptions);
  const host = new EppHost();
  await host.initialize({ base_url: mock.origin, api_key: mock.apiKey, ready_timeout: 10, ...config }, { http_timeout: 10, max_retries: 0 });
  try {
    await fn(host, mock);
  } finally {
    await host.close();
    await mock.close();
  }
}

const rpcError = async (promise) => {
  try {
    await promise;
  } catch (err) {
    return err.rpc;
  }
  assert.fail("expected an RPC error");
};

const newSandbox = async (host, params = {}) => (await host.call("sandbox.create", { template: "base", timeout: 120, ...params })).sandbox_id;

test("handshake: protocol, features, config validation", async () => {
  const host = new EppHost();
  assert.equal((await rpcError(host.call("sandbox.get", { sandbox_id: "x" }))).code, -32000);
  const bad = await rpcError(host.call("initialize", { protocol: "epp/9" }));
  assert.equal(bad.code, -32006);
  const init = await host.initialize({});
  assert.equal(init.protocol, "epp/1");
  assert.ok(init.features.includes("sandbox.lifecycle"));
  assert.ok(!init.features.includes("pty") && !init.features.includes("code.interpret"));
  assert.equal((await rpcError(host.call("no.such.method"))).code, -32601);
  assert.equal(await host.close(), 0);
});

test("undeclared features answer -32003 with the feature name", async () => {
  await withPlugin({}, {}, async (host) => {
    for (const [method, feature] of [["pty.open", "pty"], ["code.run", "code.interpret"], ["templates.list", "templates.read"], ["templates.build", "templates.build"], ["files.watch", "files.watch"], ["files.upload_url", "files.transfer"], ["process.stdin", "process.stdin"]]) {
      const err = await rpcError(host.call(method, { sandbox_id: "x" }));
      assert.equal(err.code, -32003, method);
      assert.equal(err.data.details.feature, feature, method);
    }
  });
});

test("create: request mapping, record shape and readiness", async () => {
  await withPlugin({}, { entrypoint: "sleep infinity" }, async (host, mock) => {
    const rec = await host.call("sandbox.create", {
      template: "ubuntu:22.04", timeout: 300, metadata: { name: "demo" }, envs: { A: "1" }, cpu: 2, memory: 1024, request_timeout: 30,
    });
    assert.equal(rec.status, "running");
    assert.equal(rec.template, "ubuntu:22.04");
    assert.deepEqual(rec.metadata, { name: "demo" });
    assert.ok(rec.expires_at && rec.created_at);
    assert.equal(rec.envd_url, undefined, "must not advertise an envd endpoint");
    const sent = mock.sandboxes.get(rec.sandbox_id).request;
    assert.deepEqual(sent.image, { uri: "ubuntu:22.04" });
    assert.deepEqual(sent.entrypoint, ["sleep", "infinity"]);
    assert.deepEqual(sent.resourceLimits, { cpu: "2", memory: "1024Mi" });
    assert.deepEqual(sent.env, { A: "1" });
    assert.equal(sent.secureAccess, undefined, "no secure hint from the host means the configured default (off)");
  });
});

test("create: secure and per-create options", async () => {
  await withPlugin({}, { network_policy: '{"defaultAction":"allow"}' }, async (host, mock) => {
    const explicitFalse = await host.call("sandbox.create", { template: "base", secure: false });
    assert.equal(mock.sandboxes.get(explicitFalse.sandbox_id).request.secureAccess, undefined);
    const err = await rpcError(host.call("sandbox.create", { template: "base", secure: true }));
    assert.equal(err.code, -32006, "secure=true asks for gateway secure access, which the mock refuses");

    const rec = await host.call("sandbox.create", {
      template: "base",
      options: {
        network_policy: '{"defaultAction":"deny"}',
        platform: "linux/arm64",
        default_image: "alpine:3.20",
        base_url: "http://evil.invalid",
        api_key: "stolen",
        unknown_key: 1,
      },
    });
    const sent = mock.sandboxes.get(rec.sandbox_id).request;
    assert.deepEqual(sent.networkPolicy, { defaultAction: "deny" }, "per-create option beats the configured one");
    assert.deepEqual(sent.platform, { os: "linux", arch: "arm64" });
    assert.equal(sent.image.uri, "alpine:3.20");

    const plain = await host.call("sandbox.create", { template: "base" });
    assert.deepEqual(mock.sandboxes.get(plain.sandbox_id).request.networkPolicy, { defaultAction: "allow" }, "options do not leak between creates");
  });
});

test("create: refusals and error mapping", async () => {
  await withPlugin({}, {}, async (host, mock) => {
    assert.equal((await rpcError(host.call("sandbox.create", { template: "base", disk: 1024 }))).code, -32006);
    assert.equal((await rpcError(host.call("sandbox.create", { template: "base", gpu: "A10" }))).code, -32006);
    const meta = await rpcError(host.call("sandbox.create", { template: "base", metadata: { "bad key": "v" } }));
    assert.match(meta.message, /bad key/);
    const image = await rpcError(host.call("sandbox.create", { template: "missing-image:1" }));
    assert.equal(image.code, -32002);
    assert.equal(image.data.sdk_code, "E2001");
    const rec = await host.call("sandbox.create", { template: "base", timeout: 5 });
    assert.equal(mock.sandboxes.get(rec.sandbox_id).request.timeout, 60, "ttl is clamped to the 60 s minimum");
    assert.equal(mock.sandboxes.size, 1);
  });
  await withPlugin({}, { secure_access: true }, async (host) => {
    const err = await rpcError(host.call("sandbox.create", { template: "base" }));
    assert.equal(err.code, -32006);
  });
});

test("authentication errors", async () => {
  await withPlugin({}, { api_key: "wrong-key-123" }, async (host) => {
    const err = await rpcError(host.call("sandbox.list", {}));
    assert.equal(err.code, -32001);
    assert.equal(err.data.sdk_code, "E1001");
    assert.ok(!JSON.stringify(err).includes("wrong-key-123"));
  });
  const mock = await startMock();
  const host = new EppHost();
  await host.initialize({ base_url: mock.origin });
  assert.equal((await rpcError(host.call("sandbox.list", {}))).code, -32001);
  await host.close();
  await mock.close();
});

test("an unreachable server is a retryable failure, not a crash", async () => {
  const host = new EppHost();
  await host.initialize({ base_url: "http://127.0.0.1:9", ready_timeout: 2 }, { http_timeout: 2, max_retries: 1 });
  const err = await rpcError(host.call("sandbox.list", {}));
  assert.equal(err.code, -32000);
  assert.equal(err.data.retryable, true);
  assert.match(err.message, /Cannot reach OpenSandbox/);
  await host.close();
});

test("get / connect / list / kill", async () => {
  await withPlugin({}, {}, async (host) => {
    const ids = [];
    for (const owner of ["a", "b", "a"]) ids.push(await newSandbox(host, { metadata: { owner } }));
    assert.equal((await host.call("sandbox.get", { sandbox_id: ids[0] })).sandbox_id, ids[0]);
    assert.equal((await host.call("sandbox.connect", { sandbox_id: ids[1] })).sandbox_id, ids[1]);
    const page1 = await host.call("sandbox.list", { limit: 2 });
    assert.equal(page1.sandboxes.length, 2);
    assert.equal(page1.next, "2");
    const page2 = await host.call("sandbox.list", { limit: 2, cursor: page1.next });
    assert.equal(page2.sandboxes.length, 1);
    assert.equal(page2.next, undefined);
    assert.equal((await host.call("sandbox.list", { metadata: { owner: "a" } })).sandboxes.length, 2);
    assert.equal((await host.call("sandbox.list", { status: "paused" })).sandboxes.length, 0);
    await host.call("sandbox.kill", { sandbox_id: ids[0] });
    assert.deepEqual(await host.call("sandbox.kill", { sandbox_id: ids[0] }), {}, "kill is idempotent");
    assert.equal((await rpcError(host.call("sandbox.get", { sandbox_id: ids[0] }))).code, -32002);
    assert.equal((await rpcError(host.call("sandbox.get", {}))).code, -32006);
  });
});

test("set_timeout uses the server clock; pause/resume wait for the state", async () => {
  await withPlugin({}, {}, async (host, mock) => {
    const id = await newSandbox(host);
    const res = await host.call("sandbox.set_timeout", { sandbox_id: id, timeout: 600 });
    const delta = Date.parse(mock.sandboxes.get(id).expiresAt) - Date.now();
    assert.ok(Math.abs(delta - 600_000) < 3000, `expiry ${delta} ms away`);
    assert.equal(res.expires_at, mock.sandboxes.get(id).expiresAt);
    await host.call("sandbox.pause", { sandbox_id: id });
    assert.equal((await host.call("sandbox.get", { sandbox_id: id })).status, "paused");
    assert.equal((await host.call("sandbox.list", { status: "paused" })).sandboxes.length, 1);
    await host.call("sandbox.resume", { sandbox_id: id });
    assert.equal((await host.call("sandbox.get", { sandbox_id: id })).status, "running");
    assert.equal((await rpcError(host.call("sandbox.resume", { sandbox_id: id }))).code, -32000);
  });
});

test("exec.run: output, exit codes, env, cwd, stdin, timeout", async () => {
  await withPlugin({}, {}, async (host) => {
    const id = await newSandbox(host, { envs: { FROM_CREATE: "yes" } });
    const run = (extra) => host.call("exec.run", { sandbox_id: id, timeout: 20, ...extra });
    const r = await run({ cmd: "sh", args: ["-c", "printf 'a\\r\\nb\\n'; echo err >&2; echo $FROM_CREATE $X; exit 3"], env: { X: "x" } });
    assert.deepEqual(r, { exit_code: 3, stdout: "a\r\nb\nyes x\n", stderr: "err\n" });
    assert.equal((await run({ cmd: "nonexistent-xyz", args: [] })).exit_code, 127);
    await host.call("files.mkdir", { sandbox_id: id, path: "/work/sub" });
    assert.equal((await run({ cmd: "pwd", args: [], cwd: "/work/sub" })).stdout.trim().endsWith("/work/sub"), true);
    assert.equal((await run({ cmd: "cat", args: [], stdin: "from stdin" })).stdout, "from stdin");
    assert.equal((await run({ cmd: "echo", args: ["a b", "$HOME;x"] })).stdout.startsWith("a b $HOME;x"), true);
    const timeout = await rpcError(run({ cmd: "sleep", args: ["10"], timeout: 1 }));
    assert.equal(timeout.code, -32005);
    assert.equal(timeout.data.sdk_code, "E3001");
  });
});

test("legacy execd (no argv, line-stripped events) gives the same bytes", async () => {
  await withPlugin({ legacyExecd: true }, {}, async (host) => {
    const id = await newSandbox(host);
    const r = await host.call("exec.run", { sandbox_id: id, cmd: "sh", args: ["-c", "echo one; echo 'two words'; echo err >&2; exit 2"], timeout: 20 });
    assert.deepEqual(r, { exit_code: 2, stdout: "one\ntwo words\n", stderr: "err\n" });
    const quoted = await host.call("exec.run", { sandbox_id: id, cmd: "echo", args: ["it's", "a;b"], timeout: 20 });
    assert.equal(quoted.stdout, "it's a;b\n");
  });
});

test("gateway mode: Endpoint.headers are replayed on every data-plane call", async () => {
  await withPlugin({ gateway: true }, {}, async (host) => {
    const id = await newSandbox(host);
    assert.equal((await host.call("exec.run", { sandbox_id: id, cmd: "echo", args: ["ok"], timeout: 20 })).stdout, "ok\n");
    await host.call("files.write", { sandbox_id: id, path: "/g.txt", content_b64: b64("g") });
    assert.equal((await host.call("files.read", { sandbox_id: id, path: "/g.txt" })).content_b64, b64("g"));
    await host.call("exec.start", { sandbox_id: id, cmd: "echo", args: ["s"], timeout: 20 });
    await host.waitNote((n) => n.method === "exec.exit");
    assert.deepEqual((await host.call("ports.url", { sandbox_id: id, port: 3000 })).headers, { "X-GW-Route": "1" });
  });
});

test("exec.start: ordered output notifications and exactly one final exit", async () => {
  await withPlugin({}, {}, async (host) => {
    const id = await newSandbox(host);
    const { process_id } = await host.call("exec.start", { sandbox_id: id, cmd: "sh", args: ["-c", "echo one; sleep 0.2; echo two >&2; sleep 0.2; echo three; exit 4"], timeout: 20 });
    assert.match(process_id, /^[0-9a-f]{32}$/);
    await host.waitNote((n) => n.method === "exec.exit");
    const notes = host.notes.filter((n) => n.params.process_id === process_id);
    assert.equal(notes.at(-1).method, "exec.exit");
    assert.equal(notes.at(-1).params.exit_code, 4);
    assert.equal(notes.filter((n) => n.method === "exec.exit").length, 1);
    const out = notes.filter((n) => n.method === "exec.output").map((n) => `${n.params.stream}:${n.params.data}`);
    assert.deepEqual(out, ["stdout:one\n", "stderr:two\n", "stdout:three\n"]);
  });
});

test("exec.start: failures become output + exit 127; timeouts exit 124", async () => {
  await withPlugin({}, {}, async (host) => {
    const id = await newSandbox(host);
    const a = await host.call("exec.start", { sandbox_id: id, cmd: "nonexistent-xyz", args: [], timeout: 20 });
    const exitA = await host.waitNote((n) => n.method === "exec.exit" && n.params.process_id === a.process_id);
    assert.equal(exitA.params.exit_code, 127);
    const b = await host.call("exec.start", { sandbox_id: id, cmd: "sleep", args: ["10"], timeout: 1 });
    const exitB = await host.waitNote((n) => n.method === "exec.exit" && n.params.process_id === b.process_id);
    assert.equal(exitB.params.exit_code, 124);
  });
});

test("exec.start detached: output is followed through the log cursor", async () => {
  await withPlugin({}, {}, async (host) => {
    const id = await newSandbox(host);
    const { process_id } = await host.call("exec.start", { sandbox_id: id, cmd: "sh", args: ["-c", "echo first; sleep 0.6; echo second; exit 5"], timeout: 20, detached: true });
    const exit = await host.waitNote((n) => n.method === "exec.exit" && n.params.process_id === process_id);
    assert.equal(exit.params.exit_code, 5);
    const text = host.notes.filter((n) => n.method === "exec.output").map((n) => n.params.data).join("");
    assert.equal(text, "first\nsecond\n");
  });
});

test("process.* : list, kill by pid and by command id, signal limits", { skip: !existsSync("/proc/self/stat") }, async () => {
  await withPlugin({}, {}, async (host) => {
    const id = await newSandbox(host);
    const { process_id } = await host.call("exec.start", { sandbox_id: id, cmd: "sleep", args: ["30"], timeout: 60, detached: true });
    const { processes } = await host.call("process.list", { sandbox_id: id });
    const sleeper = processes.find((p) => p.command.startsWith("sleep 30"));
    assert.ok(sleeper, JSON.stringify(processes));
    assert.equal(typeof sleeper.pid, "number");
    assert.ok(!processes.some((p) => p.command.includes("__ebx_ps__")));
    await host.call("process.signal", { sandbox_id: id, pid: sleeper.pid, signal: 15 });
    await host.waitNote((n) => n.method === "exec.exit" && n.params.process_id === process_id);
    assert.equal((await rpcError(host.call("process.kill", { sandbox_id: id, pid: 99999999 }))).code, -32002);
    const b = await host.call("exec.start", { sandbox_id: id, cmd: "sleep", args: ["30"], timeout: 60 });
    assert.equal((await rpcError(host.call("process.signal", { sandbox_id: id, pid: b.process_id, signal: 15 }))).code, -32003);
    await host.call("process.kill", { sandbox_id: id, pid: b.process_id });
    await host.waitNote((n) => n.method === "exec.exit" && n.params.process_id === b.process_id);
    assert.equal((await rpcError(host.call("process.kill", { sandbox_id: id, pid: "???" }))).code, -32006);
  });
});

test("files: round trip, binary safety, metadata, chunked reads", async () => {
  await withPlugin({}, {}, async (host) => {
    const id = await newSandbox(host);
    const f = (method, params) => host.call(method, { sandbox_id: id, ...params });
    const bytes = "\u0000\u00ff\r\n--boundary\r\nend";
    await f("files.write", { path: "/data/bin.dat", content_b64: b64(bytes), mode: 0o600 });
    const read = await f("files.read", { path: "/data/bin.dat" });
    assert.equal(Buffer.from(read.content_b64, "base64").toString("latin1"), bytes);
    assert.equal(read.size, bytes.length);
    assert.equal(read.eof, true);
    await f("files.write", { path: "/data/empty", content_b64: "" });
    assert.equal((await f("files.read", { path: "/data/empty" })).size, 0);
    const stat = await f("files.stat", { path: "/data/bin.dat" });
    assert.deepEqual([stat.name, stat.type, stat.size, stat.mode], ["bin.dat", "file", bytes.length, 600]);
    const chunk = await f("files.read", { path: "/data/bin.dat", offset: 2, length: 4 });
    assert.equal(Buffer.from(chunk.content_b64, "base64").toString("latin1"), bytes.slice(2, 6));
    assert.equal(chunk.eof, false);
    assert.equal((await f("files.read", { path: "/data/bin.dat", offset: bytes.length })).size, 0);
    const dir = await rpcError(f("files.read", { path: "/data" }));
    assert.equal(dir.data.sdk_code, "E4000");
    const missing = await rpcError(f("files.read", { path: "/nope" }));
    assert.deepEqual([missing.code, missing.data.sdk_code], [-32002, "E4001"]);
    assert.equal((await rpcError(f("files.stat", { path: "/nope" }))).code, -32002);
    assert.equal((await rpcError(f("files.write", {}))).code, -32006);
  });
});

test("files: list, mkdir, move, remove, search, chmod", async () => {
  await withPlugin({}, {}, async (host) => {
    const id = await newSandbox(host);
    const f = (method, params) => host.call(method, { sandbox_id: id, ...params });
    await f("files.mkdir", { path: "/t/a/b" });
    await f("files.mkdir", { path: "/t/a/b" });
    await f("files.write", { path: "/t/a/one.txt", content_b64: b64("1") });
    await f("files.write", { path: "/t/a/b/two.txt", content_b64: b64("22") });
    const ls = (await f("files.list", { path: "/t/a" })).entries;
    assert.deepEqual(ls.map((e) => [e.name, e.type]), [["b", "directory"], ["one.txt", "file"]]);
    assert.equal((await f("files.list", { path: "/t/a", depth: 2 })).entries.length, 3);
    assert.equal((await rpcError(f("files.list", { path: "/t/a/one.txt" }))).code, -32006);
    assert.equal((await rpcError(f("files.list", { path: "/zzz" }))).code, -32002);
    const found = (await f("files.search", { path: "/t", pattern: "**/*.txt" })).entries.map((e) => e.path);
    assert.deepEqual(found.sort(), ["/t/a/b/two.txt", "/t/a/one.txt"]);
    assert.deepEqual((await f("files.search", { path: "/t", pattern: "**/*.txt", max_depth: 2 })).entries.map((e) => e.path), ["/t/a/one.txt"]);
    await f("files.chmod", { path: "/t/a/one.txt", mode: "0700" });
    assert.equal((await f("files.stat", { path: "/t/a/one.txt" })).mode, 700);
    await f("files.move", { source: "/t/a/one.txt", destination: "/t/moved/one.txt" });
    assert.equal((await rpcError(f("files.stat", { path: "/t/a/one.txt" }))).code, -32002);
    await f("files.write", { path: "/t/other.txt", content_b64: b64("o") });
    const clash = await rpcError(f("files.move", { source: "/t/other.txt", destination: "/t/moved/one.txt" }));
    assert.equal(clash.code, -32006);
    await f("files.move", { source: "/t/other.txt", destination: "/t/moved/one.txt", overwrite: true });
    assert.equal(Buffer.from((await f("files.read", { path: "/t/moved/one.txt" })).content_b64, "base64").toString(), "o");
    await f("files.move", { source: "/t/a", destination: "/t/renamed" });
    assert.equal((await f("files.stat", { path: "/t/renamed/b/two.txt" })).size, 2);
    await f("files.remove", { path: "/t/moved/one.txt" });
    await f("files.remove", { path: "/t" });
    assert.equal((await rpcError(f("files.remove", { path: "/t" }))).code, -32002);
  });
});

test("ports.url: direct, server-proxied", async () => {
  await withPlugin({}, {}, async (host, mock) => {
    const id = await newSandbox(host);
    const direct = await host.call("ports.url", { sandbox_id: id, port: 8000 });
    assert.equal(direct.url, `${mock.origin}/execd/${id}/proxy/8000`);
    assert.equal(direct.headers, undefined);
    assert.equal((await rpcError(host.call("ports.url", { sandbox_id: id, port: 0 }))).code, -32006);
    assert.equal((await rpcError(host.call("ports.url", { sandbox_id: "ghost", port: 80 }))).code, -32002);
  });
  await withPlugin({}, { use_server_proxy: true }, async (host, mock) => {
    const id = await newSandbox(host);
    assert.equal((await host.call("ports.url", { sandbox_id: id, port: 8000 })).url, `${mock.origin}/v1/sandboxes/${id}/proxy/8000`);
  });
});

test("a paused sandbox yields a clear, retryable error for data-plane calls", async () => {
  await withPlugin({}, {}, async (host) => {
    const id = await newSandbox(host);
    await host.call("sandbox.pause", { sandbox_id: id });
    const err = await rpcError(host.call("exec.run", { sandbox_id: id, cmd: "true", args: [], timeout: 5 }));
    assert.equal(err.code, -32000);
    assert.match(err.message, /Cannot reach OpenSandbox/);
  });
});

test("shutdown exits cleanly and stderr stays quiet (no secrets)", async () => {
  const mock = await startMock({ apiKey: "super-secret-key" });
  const host = new EppHost();
  await host.initialize({ base_url: mock.origin, api_key: "super-secret-key" });
  await host.call("sandbox.list", {});
  assert.equal(await host.close(), 0);
  assert.ok(!host.stderr.includes("super-secret-key"));
  await mock.close();
});

test("garbage on stdin is answered with a parse error and does not kill the plugin", async () => {
  const host = new EppHost();
  await host.initialize({});
  host.raw("this is not json");
  await new Promise((r) => setTimeout(r, 100));
  assert.equal((await host.call("shutdown")).constructor, Object);
  await host.exited;
});
