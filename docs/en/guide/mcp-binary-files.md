# Binary files through Python MCP

The Python MCP server provides `upload_file` and `download_file` through both
STDIO and Streamable HTTP. The CLI's independent MCP implementation is unchanged.
These tools operate on the selected sandbox's files; they never open a path on
the MCP host. Keep `read_file`/`write_file` for text.

**Ownership:** like existing file tools, either binary tool adopts an explicitly
selected external sandbox into that MCP session. Session shutdown/HTTP session
delete destroys adopted sandboxes, even after a read-only download. Finish all
uses before closing that session. This differs from metadata inspection and TTL
updates, which do not adopt external resources. Explicit retained background
tasks keep their separate documented retention rules.

An upload accepts standard Base64 and overwrites the remote path:

```json
{"name":"upload_file","arguments":{"path":"/tmp/artifact.bin","content_base64":"AP8="}}
```

This writes two bytes, `00 ff`. Its result contains `success`, `bytes_written`
and `sha256`. Download the same bytes using:

```json
{"name":"download_file","arguments":{"path":"/tmp/artifact.bin"}}
```

The result contains `content_base64`, `bytes_read` and `sha256`. Decode Base64 in
your MCP client and verify the byte count/hash before saving to a client-chosen
local destination. No credential-bearing download URL or host-local path is
returned. File content is intentionally delivered to the authorized caller;
this is not secret-content filtering.

Each call accepts optional `sandbox_id`. Omission uses the existing default or
lazily creates one, matching other file tools. Existing file-tool TTL renewal
and session cleanup rules apply; binary transfer does not retain a sandbox on
disconnect or change [background-task ownership](mcp-background-tasks.md).

## Limits and errors

- Maximum decoded file: **1,048,576 bytes (1 MiB)**, including arbitrary NUL and
  non-UTF8 bytes. Empty files work. Maximum encoded upload: 1,398,104 characters;
  encoded length is checked before strict Base64 decoding. Unknown arguments,
  invalid Base64 and invalid paths fail before sandbox resolution/file writes.
- Remote paths are absolute, at most 4096 UTF-8 bytes, without NUL or parent
  traversal. The sandbox's existing filesystem permissions still apply.
- Download counts actual streamed response bytes, independently of Stat or
  Content-Length. Bounded reads request `Accept-Encoding: identity` and reject
  non-identity Content-Encoding before reading or decompressing a body; ordinary
  unlimited SDK reads retain their existing gzip behavior. Responses close on
  overflow/error/cancellation. No
  partial Base64 success is returned. Reads/writes have a 120-second tool wait
  limit; timed-out uploads may have reached the sandbox, so inspect the remote
  file before retrying. No atomic-write or resumable-transfer guarantee is made.
- The maximum-file JSON request/response fits the Python STDIO 8 MiB line limit;
  actual maximum-size STDIO and HTTP round trips are regression-tested. HTTP has
  no new global body limit; configure any reverse proxy/client to permit at
  least the Base64 payload plus JSON overhead (about 1.4 MiB). Larger/chunked or
  resumable uploads are outside this tool contract.
- Failures set MCP `isError: true` and include a static `error` plus
  `error_category`: `invalid_input`, `size_limit`, `not_found`,
  `permission_denied`, `sandbox_not_found`, `unsupported`, `timeout`, or
  `file_transfer`. Raw provider errors, credentials and file contents are not
  echoed into error messages or binary-tool logs. Failure does not imply that
  an accepted remote operation was cancelled.

## Optional SDK download bound

The ordinary SDK keeps its existing unbounded default. Callers can opt in:

```python
from agent_sandbox.models import FileSizeLimitError

try:
    data = await sandbox.files.read_bytes("/tmp/artifact.bin", max_bytes=1024 * 1024)
except FileSizeLimitError:
    # The response was closed; choose a smaller file or a different explicit limit.
    pass
```

`max_bytes` is a nonnegative integer or `None`. Overflow raises `FileSizeLimitError`
(`E4003`, a `FileOperationError`, with `limit`). This uses the existing envd
`GET /files` API, without an invented Range endpoint or stat/read size race.
Native Express create/connect support this bounded data plane. Node-provider
adapters explicitly reject bounded reads until their streaming contract is
implemented; they never fall back to unlimited reads. This release does not
claim live binary acceptance for other providers.

The byte limit is not a snapshot guarantee if another process changes the file.

See [MCP integration](mcp-integration.md) and [中文](../../zh/guide/mcp-binary-files.md).
