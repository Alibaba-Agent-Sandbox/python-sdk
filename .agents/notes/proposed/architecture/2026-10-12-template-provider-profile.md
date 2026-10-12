# Decision: CLI template profile, server stays provider-free

Status: proposed

## Problem
Template generation taught one Dockerfile (`CMD ["python3", "commands.py"]`, `WORKDIR /app`, an unconstrained `FROM`) while the Alibaba Cloud Express base image forbids `CMD` / `ENTRYPOINT` and uses platform `start_cmd` / `ready_cmd`. Those facts were starting to live on `easy_sandbox.server` and on `official_base_image()`, so every provider inherited the FC image.

## Decision
The HTTP server is not a provider. Port 9000 stays the server listen default. `commands.py` imports only `easy_sandbox.server` and calls `serve(port=9000)` under `if __name__ == "__main__"`.

The image contract is a CLI template profile: `base_image`, `entrypoint_replaceable`, `server_start` (`image_cmd` | `platform_start_cmd`), `cmd`, `start_cmd`, `ready_cmd`, `arch`, `workdir`, `reserved_ports`, and a registry note. `alicloud-express` is the built-in FC profile (no `CMD` / `ENTRYPOINT`, workdir `/home/user/app`, reserved ports 49983 / 5000 / 49999). Every other provider uses the generic profile (`FROM python:3.12-slim`, `CMD ["python3", "commands.py"]`, `WORKDIR /app`) unless `ebx-provider.toml` has a `[template]` table. A missing profile is announced and never falls through to the FC image. OpenSandbox keeps the generic profile; its create entrypoint is unchanged in this pass.

`ebx` resolves the provider the same way as the rest of the CLI (`--provider` / `EBX_PROVIDER` / default `alicloud-express`). The guide, the codegen prompt, and scaffolds describe that one profile. The client SDK does not select a provider. `official_base_image()` stays a pure string helper and the generator does not call it with no arguments. `server.contract` still holds the FC port constants, marked as the alicloud-express profile rather than the HTTP API.

## API Design
Plugin manifest table `[template]` with the fields above. No new server or client API.

## Alternatives considered
- Teach both the FC rule and the generic `CMD` rule in one prompt. Rejected: one selected profile, one Dockerfile.
- Put the FC registry, reserved ports, and start command on `easy_sandbox.server`. Rejected: the server must not import a provider.
- Treat a missing profile as `alicloud-express`. Rejected: an unknown provider is not Function Compute.

## Dependencies
CLI provider resolution (`resolveProviderId`). Server package `easy-sandbox-server` in the scaffold install snippet.

## Test Strategy
Profile selection (default, explicit provider with no profile, unknown id, declared `[template]`), guide text (FC `FROM` and no `CMD` instruction versus generic `CMD`), and scaffold Dockerfiles.

## Acceptance criteria
- Default generation uses the FC profile and does not emit `CMD` or `ENTRYPOINT`.
- A provider without `[template]` gets the generic profile and the generator names that id.
- `commands.py` does not mention a provider and does not call `serve()` at import time.
