# Testing & Definition of Done

How the Python SDK (`agent-sandbox-client`) and the in-sandbox server (`agent-sandbox-server`) are verified end to end, and the rules that decide when a change counts as done.

> 中文版: [../../zh/guide/testing-e2e.md](../../zh/guide/testing-e2e.md)

## Verification layers

| Layer | Tool | Real components? | Credentials | Typical time |
|---|---|---|---|---|
| Unit/component tests | `make test` (pytest in both packages) | Logic mocks and real local HTTP/PTY fixtures | none | seconds to minutes |
| Real-cloud E2E | `make e2e` | **Yes**: real platform, envd, in-sandbox server | `.env` or environment | ~8 min |
| E2E incl. slow cases | `make e2e-all` | **Yes** | same | longer |

Only the real-cloud layer can close the "E2E" item of the Definition of Done.

## Running the E2E suite

```bash
cp .env.example .env     # fill in real values; .env is gitignored
make e2e                 # fast path
make e2e-all             # + slow tests
make e2e-cleanup         # dry-run janitor for leftovers; ARGS=--yes deletes
```

Without credentials every test is skipped with an explicit reason, and the unit CI never collects the suite. Every sandbox created by the suite is tagged and removed in finalizers; `scripts/e2e-cleanup.py` handles runs that were killed hard. Details, markers and guarantees are in [`e2e/README.md`](../../../e2e/README.md). Product defects found by the suite are recorded as strict xfails and listed in [`e2e/KNOWN-ISSUES.md`](../../../e2e/KNOWN-ISSUES.md).

## Definition of Done

A change is done when all of the following hold:

1. Unit tests, lint and `scripts/check-repo-health.sh` pass.
2. The feature was exercised against real components (`make e2e` or a targeted E2E case), not only mocks.
3. Docs are complete in English and Chinese and a CHANGELOG entry exists.
4. Large changes are recorded as an ADR under `.agents/notes/` with the correct status.
5. Evidence (commands, results, resource cleanup) is stored in `.agents/evidence/verify/<date>-<topic>.md`, with no secrets.
6. No sandbox is leaked.

The full rules and the ADR and evidence templates: [`.agents/notes/DEFINITION-OF-DONE.md`](../../../.agents/notes/DEFINITION-OF-DONE.md).

## Cloud example practice

Outside the test suite, the walkthrough that runs the example scripts on the default provider is [Cloud end-to-end practice](cloud-examples.md). The Agents API case is not on that page; see [Agents API](agents-api.md).

## Local HTTP and PTY fixture ports

The client component fixture selects distinct HTTP and PTY port candidates before starting either listener. A released ephemeral candidate may be returned again; selection retries are bounded and preserve an explicit PTY port. These local allocation retries do not replay a request or replace real-cloud acceptance. The deterministic reuse regression starts the actual server and verifies both listeners, then normal fixture cleanup shuts them down.


## Local raw HTTP fixtures

Raw requests identify the actual listener authority. Fixtures wait for their HTTP server
to initialize within the existing deadline and read the complete framed response. An
intermediary can reject intentionally malformed HTTP/WebSocket traffic before it reaches
the handler; keep those failures visible and run the unchanged assertions in hosted CI.
Do not substitute skips, longer timeouts or proxy policy changes for protocol coverage.

## Public release readback

After uploading the paired distributions, the publication workflow compares all four
local release filenames and SHA-256 digests with PyPI. Missing metadata (HTTP 404)
gets at most six attempts, ten seconds apart; a digest mismatch fails immediately.
The separate fresh installation from the official PyPI index has the same bounded
retry interval because that index may appear later than package metadata. Each
failed installation remains visible in the log. Dependency and public import checks
run once after installation succeeds; their failures stop the release.

## SDK fixture images

The SDK repository keeps offline python-hello and agents-cli fixtures, separate
from the template catalog. Their Dockerfiles install public server 0.4.0a3 from
the official PyPI index without local wheels. CI builds both, checks the actual
guest package and HTTP application, and confirms owned container cleanup.
Agents runtime listing does not prove an installed agent or a real model call.
