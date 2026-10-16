# Decision: Import command files with normal module registration

Status: proposed

## Problem

The server CLI executes file-based commands without first registering the module in
`sys.modules`. A real `codex-agent-api` template fails during startup when its
postponed-annotation dataclass decorator resolves its defining module. The HTTP
server never starts. Repeated file arguments also execute registration side effects
again, and a failed import leaves its directory on `sys.path`.

## Decision

Canonicalize file paths with `os.path.realpath`, derive a private module name from
the SHA-256 of the filesystem-encoded path, and register the module before executing
it. Reuse successfully loaded files, including relative and symbolic-link aliases.
Separate files with the same basename remain distinct. Keep a successful file's
directory importable for deferred sibling imports. On any `BaseException`, remove
the incomplete module entry, restore the pre-load search path and propagate the
original exception. Do not attempt to roll back arbitrary user registration side
effects; startup fails and the operator fixes the file before restarting.

## API Design

The internal `_load_commands(spec: str) -> None` signature and public
`agent-sandbox-server serve --commands FILE_OR_MODULE` syntax are unchanged.
Importable module names continue through `importlib.import_module`.

## Alternatives considered

- **Remove postponed annotations from templates** — rejected because valid Python
  command modules should work through the supported CLI startup path.
- **Only register immediately before execution** — insufficient because failure
  leaves a half-initialized module and repeated arguments execute registrations again.
- **Re-execute successful files** — rejected in favor of normal import caching;
  operators restart the server when changing command files.

## Dependencies

Only Python standard-library modules; no dependency or package-version changes.

## Test Strategy

Regression tests exercise dataclasses with postponed `ClassVar` annotations,
relative/absolute/symbolic-link repeat imports, distinct same-basename files,
ordinary module imports, and failed `RuntimeError`/`SystemExit` cleanup followed by
a repaired-file retry. CLI configuration tests remain covered. The template agent
also runs the real `serve --commands` subprocess and its real HTTP test client.

## Acceptance criteria

- The previously failing dataclass command file loads through the real CLI.
- Loading the same canonical file repeats no registration side effect.
- A failed import preserves its exception, removes the incomplete module and
  restores the original search path.
- Unit, lint, type and repository gates pass, and required cloud E2E is recorded.

## Evidence

- [Verification](../../../evidence/verify/2026-10-16-server-command-loader.md)
- [SDK issue 30](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/30)

## Implementation

The fix, focused tests and an independent real-cloud source-wheel startup and
command invocation are verified in the follow-up evidence. The record remains
proposed until the exact synchronized head passes its complete remote CI and
normal review/merge gates. Historical partial evidence is preserved unchanged.

- [Cloud delivery verification](../../../evidence/verify/2026-10-16-server-loader-cloud-delivery.md)
