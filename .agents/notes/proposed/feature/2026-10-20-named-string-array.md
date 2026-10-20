# Decision: Native string-array arguments for named commands

Status: proposed

## Problem

Media processing and other templates need argument vectors that preserve spaces,
Unicode and individual values. The existing server infers `list[str]` as string,
so a real JSON request returns a Python representation instead of the array.
Declarative registration rejects this annotation. See
[Issue 76](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/76) and the
[Media template issue](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/58).

## Decision

Add the explicit `string_array` metadata type for homogeneous native JSON string
arrays. Both coercers validate every element and copy supplied arrays. Defaults
retain the existing string-valued metadata field, using validated JSON text and
fresh decoding per invocation. Do not add shell parsing or JSON-string coercion.
The four scalar types keep their existing behavior and errors.
[Issue 77](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/77)
repairs existing E2E prerequisites: native async imports and explicit uninstalled
provider refusal. Credential validation remains required for installed providers. The standalone
server registry remains independent of upper SDK layers and external packages.

## API Design

`@command` and `@sandbox.register` infer `list[str]` and `typing.List[str]` as
`string_array`. Explicit `CommandArg(type="string_array", name="args")` is accepted.
`server_client.commands.run("array_echo", args=["literal file.wav", "中文"])`
forwards a native JSON array. Invalid types and missing required fields return400.
The CLI needs no implementation change because its JSON object is preserved.
Older servers require rebuilding before an array command can be exposed.

## Alternatives considered

- Encode arrays into a string: ambiguous and hides the protocol defect.
- Introduce arbitrary JSON values: unnecessary scope and harder validation.
- Replace the existing scalar/default fields: breaks existing clients.

## Dependencies

Python stdlib `json` and `typing`; no new distribution dependency. The Media
consumer will explicitly pin the immutable server commit after this change lands.

## Test Strategy

A preregression sends real HTTP to the actual server and fails because the result
is a string. Cover native arrays, mixed values, null, required fields, mutation
isolation and declarative registration. Keep the existing coercer parity test.
The new Express tests upload the checkout server source into fresh owned
sandboxes, verify its digest, call through the Python client and native CLI,
and use the existing tracker/finalizers for cleanup. Poll only the known
asynchronous forwarded-port readiness transition. Run the repository's full
unit, static, distribution, health, hygiene and real-cloud gates.

## Acceptance criteria

- Native arrays preserve exact values; invalid inputs never invoke the function.
- Default mutation cannot affect later calls and callers keep their own array.
- Existing scalar and metadata contracts remain compatible.
- Actual Express Python client and CLI JSON requests pass on the changed server.
- Every required repository check passes and owned cloud resources are absent.
- English/Chinese docs, changelog and verification evidence accompany the PR.

## Evidence

- [Verification](../../../evidence/verify/2026-10-20-named-string-array.md)
