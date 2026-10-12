// Incremental parser for execd's event stream.
//
// execd answers with `Content-Type: text/event-stream` but frames are *bare JSON objects*
// separated by a blank line (no `data:` prefix). Standard `data: {...}` frames are accepted too.

export class SseParser {
  constructor() {
    this.pending = "";
    this.frame = [];
  }

  /** Feed decoded text; returns the events completed by it. */
  push(text) {
    this.pending += text;
    const events = [];
    let nl;
    while ((nl = this.pending.indexOf("\n")) >= 0) {
      let line = this.pending.slice(0, nl);
      this.pending = this.pending.slice(nl + 1);
      if (line.endsWith("\r")) line = line.slice(0, -1);
      this.#line(line, events);
    }
    return events;
  }

  /** Flush at end of stream. */
  end() {
    const events = [];
    if (this.pending) {
      this.#line(this.pending.endsWith("\r") ? this.pending.slice(0, -1) : this.pending, events);
      this.pending = "";
    }
    this.#flush(events);
    return events;
  }

  #line(line, events) {
    if (line === "") {
      this.#flush(events);
      return;
    }
    if (line.startsWith(":") || /^(event|id|retry):/.test(line)) return;
    this.frame.push(line.startsWith("data:") ? line.slice(5).replace(/^ /, "") : line);
    // Streams of single-line frames without blank separators are tolerated: a complete JSON line is an event.
    if (this.frame.length === 1 && line.trimEnd().endsWith("}")) {
      const parsed = tryParse(this.frame[0]);
      if (parsed !== undefined) {
        events.push(parsed);
        this.frame = [];
      }
    }
  }

  #flush(events) {
    if (this.frame.length === 0) return;
    const text = this.frame.join("\n");
    this.frame = [];
    const parsed = tryParse(text);
    if (parsed !== undefined) events.push(parsed);
  }
}

function tryParse(text) {
  try {
    const value = JSON.parse(text);
    return value && typeof value === "object" && !Array.isArray(value) ? value : undefined;
  } catch {
    return undefined;
  }
}

/** Async iterator over the events of a fetch `Response` body. */
export async function* readEvents(response) {
  const parser = new SseParser();
  const decoder = new TextDecoder("utf-8");
  for await (const chunk of response.body) {
    for (const event of parser.push(decoder.decode(chunk, { stream: true }))) yield event;
  }
  for (const event of parser.push(decoder.decode())) yield event;
  for (const event of parser.end()) yield event;
}
