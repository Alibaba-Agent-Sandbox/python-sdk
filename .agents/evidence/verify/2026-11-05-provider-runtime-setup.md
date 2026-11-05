# Verification: Provider runtime setup documentation

- Date: 2026-11-05
- Base: daabf3cc12fbbc877cb2942c35578d8424f6cc3b
- Change: bilingual provider guides, CHANGELOG, proposed process note and evidence index.
- Result: PARTIAL — local document checks and the public-binary installation/handshake pass; current-head CI and review are pending.
- Scope: documentation only; no production Python source, dependency, package version or automatic installer behavior changed.

## What was verified

Source inspection confirms the SDK resolves ABX_BIN or PATH for abx and starts the engine on demand. The published Python dependency metadata has no opensandbox extra. Registry installation downloads an archive and verifies SHA-256 rather than invoking Git. Official CLI release v0.5.8 lists standalone binaries and SHA-256 assets for macOS x64/arm64, Linux x64/arm64 and Windows x64.

The public guides describe those existing installation choices, local engine reuse, OpenSandbox configuration and cleanup, and workload-dependent performance costs. No synthetic timing is promoted to a public SDK benchmark.

## Commands run

- `bash scripts/check-repo-health.sh` — exit 0: 106 passes, one existing warning (optional release guide missing), zero failures.
- `make hygiene` — exit 0: no local paths or credential-like strings found.
- Python AST parsing — all four Python blocks per language parsed; both added TOML snippets parsed.
- `sh -n` on the documented shell installer command — exit 0 in both languages.
- Changed-guide relative Markdown targets — all resolve.
- `git diff --check` — exit 0.

Real installation used the following command shapes under a fresh temporary HOME and empty working directory. EVIDENCE and SDK_PYTHON refer to task-owned locations:

```sh
uv venv "$EVIDENCE/venv" --python /usr/local/bin/python
uv pip install --python "$SDK_PYTHON" agent-sandbox-client==0.4.0a6
# Saved official installer, with ABX_VERSION=0.5.8 and a task-owned ABX_INSTALL_DIR:
/bin/sh "$EVIDENCE/install.sh"
"$ABX_BIN" --version
"$SDK_PYTHON" -m agent_sandbox.providers install registry:opensandbox --yes
"$SDK_PYTHON" -m agent_sandbox.providers --json doctor opensandbox
"$SDK_PYTHON" -m agent_sandbox.providers --json doctor opensandbox
```

The website installer at `https://www.agent-sandbox.cn/install.sh` was separately fetched (HTTP 200), saved and actually executed with the same restricted tools and another owned installation directory. No user credentials were loaded. Proxy/CA variables needed for downloads were retained without recording their values.

## Results

| Scenario | Result | Scope |
| --- | --- | --- |
| Standalone GitHub release installer | PASS | abx 0.5.8 Linux x64 installed after checksum validation |
| Website one-line installer | PASS | Actual installer execution produced the same release binary SHA-256 |
| Clean public Python installation | PASS | Python 3.13.13, client/server 0.4.0a6 in a new virtual environment |
| Default verified registry install | PASS | OpenSandbox 0.5.1 installed without --no-verify |
| Two independent Python doctor processes | PASS | installed, integrity, config and handshake checks all true |
| Shared engine reuse | PASS | Installation and both doctors retained one live engine PID; protocol abx-engine/1, version 0.5.8 |
| External tooling isolation | PASS | node, npm, git and abx were absent from the runtime PATH; ABX_BIN selected the owned binary |
| Bilingual document/static checks | PASS | Syntax, relative links, health and hygiene as listed above |

The installed GitHub binary, independently downloaded published checksum and website-installed binary all matched `69a55b0486acb1c8dcb85ef1277984a800ba946778c3cec5b009691a32212802`. This proves the embedded-runtime setup path without separate Node/npm/Git, not server deployment or backend operation readiness.

The environment was Linux x86_64 (glibc 2.41), Python 3.13.13 and uv 0.11.28. The fresh HOME isolated SDK configuration; the SDK currently derives its configuration directory from Path.home() and does not honor ABX_CONFIG_DIR. The custom binary destinations were outside PATH, and both installers correctly printed PATH advice. The SDK path succeeded through ABX_BIN.

[Safe installation metadata](2026-11-05-provider-runtime-installation.json) preserves exit codes, durations, sanitized command output and engine reuse/cleanup booleans. Engine PID/token values and private environment values are excluded. Task-owned locations are represented symbolically.

## Synthetic forwarding observation

The original safe probe files are preserved as historical text attachments: [Python probe](provider-runtime-setup-probe/probe.py.txt), [backend](provider-runtime-setup-probe/backend.cjs.txt), [forwarder](provider-runtime-setup-probe/bridge.cjs.txt), and [original results](provider-runtime-setup-probe/results.json). Source bytes are unchanged; these attachments are not product scripts, CI inputs or new executable entry points. They compare a Python httpx direct request to a localhost backend with a request through an additional minimal Node HTTP/JSON forwarder. Connections are reused; requests are serial and alternating after warmup. The environment was Linux x64, Node 22.22.2, httpx 0.28.1.

| JSON stdout bytes | Samples per path | Direct median ms | Forwarded median ms | Median difference ms |
| --- | --- | --- | --- | --- |
| 1,024 | 400 | 4.6841 | 8.6018 | 3.9178 |
| 65,536 | 150 | 4.7061 | 9.0484 | 4.3423 |
| 1,048,576 | 40 | 10.5209 | 23.2580 | 12.7371 |

These are the prior local probe's results, not a new run during this documentation edit. The probe does not run abx, the actual provider or a cloud backend. It cannot establish the complete SDK delta, file throughput, concurrency behavior or a portable performance guarantee. Its owned child processes were stopped by its finally block; the original output confirmed both had exited.

## Cleanup

No cloud resources were created by the document or binary/handshake checks. Only the engine whose command line matched the task-owned binary was signaled; it stopped successfully. Its runtime record/token and log were removed. No existing user engine was touched. Temporary binary and package installations are task-owned local files.

## Problems found

The existing guide placed --json after the Python list subcommand although the parser defines it as a global argument. Both examples now place --json before list.

The first restricted-PATH installer probe omitted mkdir, so it stopped after checksum verification and before creating the destination directory. Adding mkdir to the probe tools allowed the unchanged installer to pass. This is a probe configuration error, not a product defect; [the original sanitized result](2026-11-05-provider-runtime-installation-initial-probe-error.json) is retained.

## Not verified

No OpenSandbox server deployment, sandbox creation, command execution, file transfer or deletion was tested in the installation/handshake probe. No complete SDK-versus-native-backend benchmark, cloud-provider matrix, Linux arm64/Windows/macOS execution or new package publication is claimed. The Python example is syntax-checked; its backend operations require a running reachable service. Required remote current-head CI and review are pending.
