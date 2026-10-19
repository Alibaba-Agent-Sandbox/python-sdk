# Decision: Dispatch native server startup before readiness

Status: proposed

## Problem

The native helper returned a lazy process stream without iterating it. A healthy response could be accepted before any process Start request. Existing tests replaced the stream with an opaque object and missed the dispatch boundary.

## Decision

Drain the actual lazy stream in a bounded-memory task, await a remote process acknowledgement even with wait=False, reject early exit/failed startup, and release local readers at close/kill without killing retained remote resources. Keep standard clients and provider ownership unchanged.

## API Design

ProviderSandbox.start_server keeps its parameters and ServerClient result. wait=False skips health polling only. Startup errors omit raw process output and point callers to the executable/process PATH. A command override can use the installed Python module.

## Alternatives considered

Changing every CommandsModule background call would broaden its lazy-stream contract. Accepting only health reproduces the false-ready defect. A detached shell workaround alone would not fix the SDK helper.

## Dependencies

Python asyncio and existing StreamReader/process acknowledgement contract; no new runtime dependency. Fixes https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/69 .

## Test Strategy

Reproduce zero dispatch with a real lazy reader, then verify acknowledgement, wait=False, timeout, safe failure, process exit during health, and local-reader cleanup. Build paired wheels, install in a clean consumer and exercise real Express named commands/retention/cleanup locally. Run full tests, typing, lint and hosted matrix.

## Acceptance criteria

New behavior regressions pass; clean artifacts install with matched versions; real named command and retained-server receipt passes; no owned sandbox remains; latest-head required CI passes before merge. Source installation recipes pin a tested immutable implementation.
