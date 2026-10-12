// multipart/form-data body for execd `POST /files/upload`.
//
// execd quirk: the `metadata` part must be sent as a *file part* (with a filename);
// a plain form field is rejected with `400 metadata file is missing`.

import { randomUUID } from "node:crypto";

export function buildUpload({ path, mode, content }) {
  const boundary = `----ebx-opensandbox-${randomUUID()}`;
  const metadata = { path };
  if (mode !== undefined) metadata.mode = mode;
  const filename = (String(path).split("/").pop() || "file").replace(/["\r\n\\]/g, "_");
  const head = (name, fname, type) =>
    Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="${name}"; filename="${fname}"\r\nContent-Type: ${type}\r\n\r\n`,
    );
  const crlf = Buffer.from("\r\n");
  const body = Buffer.concat([
    head("metadata", "metadata", "application/json"),
    Buffer.from(JSON.stringify(metadata)),
    crlf,
    head("file", filename, "application/octet-stream"),
    Buffer.from(content),
    crlf,
    Buffer.from(`--${boundary}--\r\n`),
  ]);
  return { body, contentType: `multipart/form-data; boundary=${boundary}` };
}
