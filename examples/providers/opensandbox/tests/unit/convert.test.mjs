import test from "node:test";
import assert from "node:assert/strict";
import {
  validateMetadata, mapState, statusToStates, cpuLimit, memoryLimit, gpuLimit, ttlSeconds, parseAliasMap,
  shellSplit, shellQuote, shellJoin, resolveImage, isCodeInterpreterImage, endpointUrl, modeDigits, fileEntry,
  exitFromErrorEvent, restoreLineEnding, parseHttpDate, basename,
} from "../../src/convert.mjs";

test("metadata follows Kubernetes label rules", () => {
  assert.deepEqual(validateMetadata({ name: "demo", "app.io/owner": "a_b-c.1", empty: "" }), { name: "demo", "app.io/owner": "a_b-c.1", empty: "" });
  assert.throws(() => validateMetadata({ "bad key": "x" }), /Invalid metadata key 'bad key'/);
  assert.throws(() => validateMetadata({ k: "has space" }), /Invalid metadata value for 'k'/);
  assert.throws(() => validateMetadata({ k: "x".repeat(64) }), /at most 63/);
  assert.throws(() => validateMetadata({ "Bad_Prefix/k": "v" }), /DNS subdomain/);
  assert.deepEqual(validateMetadata({ n: 5 }), { n: "5" });
});

test("state/status maps are inverse enough", () => {
  assert.equal(mapState("Running"), "running");
  assert.equal(mapState("Pausing"), "paused");
  assert.equal(mapState("Terminated"), "stopped");
  assert.equal(mapState("SomethingNew"), "error");
  assert.deepEqual(statusToStates("paused"), ["Paused", "Pausing"]);
  assert.deepEqual(statusToStates(undefined), []);
  assert.deepEqual(statusToStates("bogus"), []);
});

test("resource conversions", () => {
  assert.equal(cpuLimit(undefined), "500m");
  assert.equal(cpuLimit(2), "2");
  assert.equal(cpuLimit(0.5), "500m");
  assert.equal(memoryLimit(undefined), "512Mi");
  assert.equal(memoryLimit(2048), "2048Mi");
  assert.equal(gpuLimit(undefined), undefined);
  assert.equal(gpuLimit("2"), "2");
  assert.throws(() => gpuLimit("A10"), /numeric GPU count/);
  assert.throws(() => cpuLimit(-1), /Invalid cpu/);
});

test("ttl is clamped to the server minimum", () => {
  assert.deepEqual(ttlSeconds(300), { timeout: 300, clamped: false });
  assert.deepEqual(ttlSeconds(5), { timeout: 60, clamped: true });
  assert.deepEqual(ttlSeconds(undefined), { timeout: undefined, clamped: false });
  assert.throws(() => ttlSeconds(0), /Invalid timeout/);
});

test("alias maps and entrypoints", () => {
  assert.deepEqual(parseAliasMap("a=x:1, b=y/z"), { a: "x:1", b: "y/z" });
  assert.deepEqual(parseAliasMap(["a=1", "bad"]), { a: "1" });
  assert.deepEqual(parseAliasMap(""), {});
  assert.deepEqual(shellSplit(`sh -c "echo 'a b'" ''`), ["sh", "-c", "echo 'a b'", ""]);
  assert.throws(() => shellSplit(`echo "x`), /Unterminated/);
});

test("shell quoting round-trips through sh", () => {
  assert.equal(shellQuote("plain-1.2/x"), "plain-1.2/x");
  assert.equal(shellQuote("a b"), "'a b'");
  assert.equal(shellQuote("it's"), `'it'\\''s'`);
  assert.equal(shellQuote(""), "''");
  assert.equal(shellJoin(["echo", "a;b", "$HOME"]), "echo 'a;b' '$HOME'");
});

test("template -> image", () => {
  const cfg = { defaultImage: "python:3.12-slim", imageAliases: { code: "opensandbox/code-interpreter:v1.1.0" } };
  assert.equal(resolveImage("base", cfg), "python:3.12-slim");
  assert.equal(resolveImage("", cfg), "python:3.12-slim");
  assert.equal(resolveImage("code", cfg), "opensandbox/code-interpreter:v1.1.0");
  assert.equal(resolveImage("ubuntu:22.04", cfg), "ubuntu:22.04");
  assert.equal(resolveImage("toString", cfg), "toString");
  assert.ok(isCodeInterpreterImage("opensandbox/code-interpreter:v1.1.0"));
  assert.ok(isCodeInterpreterImage("registry.example.com/opensandbox/code-interpreter"));
  assert.ok(!isCodeInterpreterImage("python:3.12"));
});

test("endpoint urls", () => {
  assert.equal(endpointUrl("10.0.0.1:8080/proxy/80", "http"), "http://10.0.0.1:8080/proxy/80");
  assert.equal(endpointUrl("https://gw.example.com/x", "http"), "https://gw.example.com/x");
});

test("file modes: execd wants octal digits as a decimal int", () => {
  assert.equal(modeDigits(0o644), 644);
  assert.equal(modeDigits("0755"), 755);
  assert.equal(modeDigits("0o700"), 700);
  assert.equal(modeDigits(undefined), undefined);
  assert.throws(() => modeDigits("9"), /octal/);
});

test("file entries", () => {
  assert.equal(basename("/a/b/c.txt"), "c.txt");
  assert.equal(basename("/"), "/");
  const e = fileEntry({ path: "/a/b", type: "symlink", size: 3, modified_at: "2026-01-01T00:00:00Z", mode: 777 });
  assert.deepEqual(e, { name: "b", path: "/a/b", type: "file", size: 3, mtime: "2026-01-01T00:00:00Z", symlink: true, mode: 777 });
  assert.equal(fileEntry({ path: "/d", type: "directory", size: 0 }).type, "directory");
});

test("exit status from execd error events", () => {
  assert.deepEqual(exitFromErrorEvent({ ename: "CommandExecError", evalue: "3", traceback: ["exit status 3"] }).exitCode, 3);
  const killed = exitFromErrorEvent({ evalue: "-1", traceback: ["signal: killed"] });
  assert.ok(killed.killed);
  const missing = exitFromErrorEvent({ evalue: 'exec: "nope": executable file not found in $PATH' });
  assert.equal(missing.exitCode, 127);
  assert.equal(exitFromErrorEvent({ evalue: "permission denied" }).exitCode, 126);
});

test("legacy line endings and dates", () => {
  assert.equal(restoreLineEnding("abc"), "abc\n");
  assert.equal(restoreLineEnding("abc\n"), "abc\n");
  assert.equal(restoreLineEnding("abc\r"), "abc\r");
  assert.equal(parseHttpDate("Mon, 12 Oct 2026 10:00:00 GMT"), Date.UTC(2026, 9, 12, 10));
  assert.equal(parseHttpDate("garbage"), undefined);
  assert.equal(parseHttpDate(null), undefined);
});
