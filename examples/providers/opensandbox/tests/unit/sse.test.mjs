import test from "node:test";
import assert from "node:assert/strict";
import { SseParser, readEvents } from "../../src/sse.mjs";
import { buildUpload } from "../../src/multipart.mjs";

const parse = (chunks) => {
  const p = new SseParser();
  const out = chunks.flatMap((c) => p.push(c));
  return [...out, ...p.end()];
};

test("bare JSON frames separated by blank lines", () => {
  const events = parse(['{"type":"init","text":"abc"}\n\n{"type":"stdout","text":"hi\\n"}\n\n']);
  assert.deepEqual(events.map((e) => e.type), ["init", "stdout"]);
  assert.equal(events[1].text, "hi\n");
});

test("standard data: framing, CRLF and comments", () => {
  const events = parse([": ping\r\n", 'event: message\r\ndata: {"type":"stdout","text":"x"}\r\n\r\n', 'data:{"type":"stderr","text":"y"}\r\n\r\n']);
  assert.deepEqual(events.map((e) => e.text), ["x", "y"]);
});

test("frames split across arbitrary chunk boundaries", () => {
  const raw = '{"type":"stdout","text":"hello wörld\\n"}\n\n{"type":"execution_complete"}\n\n';
  for (let cut = 1; cut < raw.length; cut += 7) {
    const events = parse([raw.slice(0, cut), raw.slice(cut)]);
    assert.equal(events.length, 2, `cut at ${cut}`);
  }
});

test("a final frame without blank line is flushed; junk is dropped", () => {
  assert.equal(parse(['{"type":"a"}']).length, 1);
  assert.equal(parse(["not json\n\n"]).length, 0);
  assert.equal(parse(["[1,2]\n\n"]).length, 0);
});

test("single-line events without separators are not merged", () => {
  assert.equal(parse(['{"type":"a"}\n{"type":"b"}\n']).length, 2);
});

test("readEvents decodes multi-byte characters split across chunks", async () => {
  const bytes = Buffer.from('{"type":"stdout","text":"é€"}\n\n');
  const body = (async function* () { yield bytes.subarray(0, 25); yield bytes.subarray(25); })();
  const out = [];
  for await (const ev of readEvents({ body })) out.push(ev);
  assert.equal(out[0].text, "é€");
});

test("multipart: metadata is a file part, bytes are preserved", () => {
  const content = Buffer.from([0, 255, 10, 13, 45, 45]);
  const { body, contentType } = buildUpload({ path: "/tmp/a b.bin", mode: 644, content });
  const boundary = /boundary=(.+)$/.exec(contentType)[1];
  const text = body.toString("latin1");
  assert.match(text, /name="metadata"; filename="metadata"/);
  assert.match(text, /name="file"; filename="a b.bin"/);
  assert.ok(text.includes('{"path":"/tmp/a b.bin","mode":644}'));
  assert.ok(body.includes(content));
  assert.ok(text.endsWith(`--${boundary}--\r\n`));
});
