# Verification: SDK target identities and lifetimes

- Date: 2026-11-25
- Result: PASS (documentation scope)
- Baseline: python-sdk 76c7e68bd9cc73f52c4ddf9545656ed4bcd1f847
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/179

## What was verified

Source audit confirmed ProviderSandbox.connect takes a Sandbox ID and explicit/default Provider context; close releases local resources; kill requests remote deletion; __aexit__ attempts kill for connected as well as created instances. ServerClient is an HTTP client. Existing managed API docs already distinguish acceptance, Turn completion, idempotency, cancel/close and File/artifact lifetimes; this change links those existing contracts rather than creating a new SDK wrapper.

## Commands and results

- `bash scripts/check-repo-health.sh --quiet`: PASS=106, WARN=1, FAIL=0. Existing warning: optional release maintainer guide absent.
- `make hygiene`: passed; no local paths or credential-like strings found.
- Read actual Python signatures and implementations in client-sdk/src/agent_sandbox/api/sandbox.py and server_client.py and the current managed API guide.

## Review and limits

First-round triage found the transport/identity explanation gap; Node SDK already describes its HTTP-only target correctly and was left unchanged. Root adversarial review requested current source behavior only and no claims from unmerged Provider drafts. This change is documentation-only: no package release, runtime test, cloud resource or credential change. Document/record checks are rerun on the completed diff before commit.
