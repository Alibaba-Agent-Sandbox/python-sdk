import test from "node:test";
import assert from "node:assert/strict";
import { mapHttpError, parseErrorBody, redact, CODES } from "../../src/errors.mjs";
import { parseConfig, normalizeBaseUrl } from "../../src/config.mjs";

test("the three error body shapes and non-JSON bodies", () => {
  assert.deepEqual(parseErrorBody('{"code":"X::Y","message":"boom"}'), { code: "X::Y", message: "boom" });
  const v = parseErrorBody('{"detail":[{"type":"missing","loc":["body","timeout"],"msg":"too small"}]}');
  assert.equal(v.message, "timeout: too small");
  assert.equal(parseErrorBody('{"error":"Unauthorized: x"}').message, "Unauthorized: x");
  assert.equal(parseErrorBody("<html><body>502 Bad Gateway</body></html>").message, "502 Bad Gateway");
  assert.equal(parseErrorBody("").message, "");
});

test("HTTP -> EPP error mapping", () => {
  const m = (status, body, ctx) => mapHttpError(status, JSON.stringify(body), ctx);
  assert.equal(m(401, { code: "INVALID_API_KEY", message: "no" }).code, CODES.AUTH);
  assert.equal(m(401, { code: "INVALID_API_KEY", message: "no" }).data.sdk_code, "E1001");
  assert.equal(m(404, { code: "DOCKER::SANDBOX_NOT_FOUND", message: "x" }).code, CODES.NOT_FOUND);
  assert.equal(m(404, { code: "FILE_NOT_FOUND", message: "x" }).data.sdk_code, "E4001");
  assert.equal(m(404, { code: "NOPE", message: "x" }, { what: "file" }).data.sdk_code, "E4001");
  assert.equal(m(422, { detail: [{ loc: ["body", "t"], msg: "bad" }] }).code, CODES.BAD_PARAMS);
  assert.equal(m(400, { code: "SANDBOX::INVALID_METADATA_LABEL", message: "x" }).code, CODES.BAD_PARAMS);
  assert.equal(m(501, { code: "FSB::API_NOT_SUPPORTED", message: "x" }).code, CODES.NO_FEATURE);
  assert.equal(m(500, { code: "RUNTIME_ERROR", message: "language runtime server not configured" }).data.feature, "code.interpret");
  const pull = m(500, { code: "DOCKER::SANDBOX_IMAGE_PULL_FAILED", message: "pull access denied" });
  assert.equal(pull.code, CODES.NOT_FOUND);
  assert.equal(pull.data.sdk_code, "E2001");
  assert.equal(m(429, { message: "slow down" }).code, CODES.QUOTA);
  assert.equal(m(429, { message: "slow down" }).data.retryable, true);
  assert.equal(m(403, { code: "KUBERNETES::QUOTA_EXCEEDED", message: "q" }).code, CODES.QUOTA);
  assert.equal(m(502, { code: "BACKEND_CONNECTION_FAILED", message: "x" }).data.retryable, true);
  assert.equal(m(409, { message: "conflict" }).code, CODES.FAIL);
  assert.equal(mapHttpError(502, "<html>Bad Gateway</html>").code, CODES.FAIL);
});

test("secrets are redacted", () => {
  assert.equal(redact("key=abcd1234 and abcd1234", ["abcd1234"]), "key=*** and ***");
  assert.equal(redact("abc", ["abc"]), "abc");
});

test("base url normalisation", () => {
  assert.equal(normalizeBaseUrl("http://h:8080/v1/"), "http://h:8080");
  assert.equal(normalizeBaseUrl("https://h/prefix/v1"), "https://h/prefix");
  assert.throws(() => normalizeBaseUrl("ftp://h"), /http and https/);
  assert.throws(() => normalizeBaseUrl("nonsense"), /Invalid base_url/);
});

test("configuration precedence and validation", () => {
  const d = parseConfig({}, {});
  assert.equal(d.apiBase, "http://127.0.0.1:8080/v1");
  assert.equal(d.apiKey, undefined);
  assert.equal(d.readyTimeout, 60);
  assert.deepEqual(d.imageAliases, { code: "opensandbox/code-interpreter:v1.1.0" });
  const c = parseConfig({ domain: "osb.example.com:9000", protocol: "https", api_key: "secret-key", use_server_proxy: "true", entrypoint: "sleep infinity", network_policy: '{"defaultAction":"deny"}', platform: "linux/arm64" }, { http_timeout: 12.5, max_retries: 1 });
  assert.equal(c.apiBase, "https://osb.example.com:9000/v1");
  assert.equal(c.scheme, "https");
  assert.equal(c.useServerProxy, true);
  assert.deepEqual(c.entrypoint, ["sleep", "infinity"]);
  assert.deepEqual(c.networkPolicy, { defaultAction: "deny" });
  assert.deepEqual(c.platform, { os: "linux", arch: "arm64" });
  assert.equal(c.httpTimeoutMs, 12500);
  assert.equal(c.maxRetries, 1);
  assert.deepEqual(c.secrets, ["secret-key"]);
  assert.equal(parseConfig({ base_url: "http://a:1", domain: "b:2" }).apiBase, "http://a:1/v1");
  assert.throws(() => parseConfig({ network_policy: "{oops" }), /JSON/);
  assert.throws(() => parseConfig({ platform: "plan9/mips" }), /Invalid platform/);
  assert.throws(() => parseConfig({ ready_timeout: "0" }), /ready_timeout/);
  assert.throws(() => parseConfig({ use_server_proxy: "maybe" }), /boolean/);
  assert.throws(() => parseConfig({ protocol: "ftp" }), /protocol/);
});
