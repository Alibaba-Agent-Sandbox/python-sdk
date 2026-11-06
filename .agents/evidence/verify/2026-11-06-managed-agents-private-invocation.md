# Verification: FC private invocation media conversion

- Date: 2026-11-06
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/156, continuation of `d74a26d945924ff3afdba4af55a5d065f6f57b16`.
- Result: PARTIAL — the new real HTTP regressions pass; complete new CI, final package identity and cloud acceptance remain separate gates.
- Package: matching client/server 0.4.0a7 candidate; no publication by this verifier.

## Evidence and reviewed scope

After a separately reviewed CLI configuration repair, one exact owned Dispatcher native STATUS
call returned transport status 200 containing `unsupported_media_type`, `invalid_request_error`
and the static message `Use application/json`. The private tail has no traceback. This establishes
that the HTTP handler was reached, not that the database or downstream execution succeeded.
The original private response and prior configuration failure remain preserved by the controller;
no credential, function identity or raw cloud log is copied here.

The official [FC Web-function conversion reference](https://help.aliyun.com/en/functioncompute/web-functions)
specifies `POST /invoke` with `Content-Type: application/octet-stream` for InvokeFunction;
the underlying HTTP status and headers are not preserved. The locked Node and Python generated
OpenAPI SDKs also set that type for streamed request bodies. Changing the CLI request header
would not establish compatibility with this conversion or the Python Worker sender.

Two independent reviewers accepted a default-false media option on the existing JSON body
parser. Only the existing non-Gateway exact POST `/invoke` branch enables it. JSON object and
finite-value validation, byte budget, complete length, rejection of chunked request bodies,
canonical role-scoped HMAC and application identity checks are unchanged. Existing query routing
is unchanged. Public resource requests still require JSON, and other private routes remain 404.

## Commands and actual results

- New focused command: `python -m pytest tests/test_managed_agents.py -k 'private_fc_octet or gateway_still_requires' -q`.
- PASS: 5 cases, zero skipped, 6.12 seconds. Dispatcher and Worker are each exercised over actual
  localhost HTTP against both SQLite and real PostgreSQL 16.2; public Gateway media rejection is
  exercised separately. A blank owned logical Session avoids any model or Provider operation.
- Accepted media includes existing JSON, octet-stream, and mixed-case MIME with a charset.
  Wrong role and signature return 401; malformed, non-object and non-finite JSON return 400;
  unrelated route/method return 404; unrelated media returns 415; declared oversize returns 413
  before reading the absent payload. Public octet-stream resource input remains 415.
- The first harness run had 3 passing and 2 failing cases because its Dispatcher STATUS omitted
  the required application identity; the existing 403 guard worked correctly. The fixture was
  corrected, not the guard. That result is not presented as the product's pre-fix reproduction.
- Ruff on the changed source and tests passes. Complete local and remote gates run on the new
  revision; their results will be recorded separately from the preceding frozen wheel set.

## Cleanup and limits

Every local HTTP server is shut down and its thread joined. Each real PostgreSQL fixture owns
its exact temporary data directory and deletes it. No Sandbox, cloud function, management Key,
real model task or external state is created by these regression cases. The original cloud
deployment remains under its controller's receipt and normal drain/cleanup process.

This change does not turn transport 200 into business success. Callers must still reject an
error envelope. It does not prove final FC end-to-end execution, live cloud SSE or public package
installation; the older CI wheels remain historical and do not contain this correction.
