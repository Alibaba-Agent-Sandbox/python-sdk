# Verification: provider namespaces and capability ownership

- Date: 2026-10-16
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/47; https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/36
- Result: PARTIAL
- Environment: Linux x64, Python 3.13.13, editable client/server; no new cloud operation in this review.

## What was verified

ProviderSandbox owns installed-provider routing. Standard root Sandbox/AsyncSandbox and code_interpreter are fixed E2B protocol clients: changing ABX_PROVIDER does not reinterpret their protocol as OpenSandbox. This distinction is now explicit in both provider guides and contributor instructions.

## Commands run

- Provider registry/provider sandbox/standard contract regression files: 62 passed (11.54 seconds).
- Maintained source lint, typecheck and formatting: PASS (56 server / 86 client files checked by mypy).
- Full client test rerun and repository gates were started; final summaries require their own follow-up record. No full-suite pass is inferred here.

## Results

Unknown provider namespaces no longer become opaque IDs on the default backend: E8001 is raised before requests. Empty namespaced IDs raise E8002. Existing explicit-provider conflicts retain E8030. The Express adapter declares its own 15 feature IDs, independently of the host registry, and does not advertise generic storage.mount, network.vpc or ports.domain. Those omissions describe this adapter, not the cloud service's complete capabilities.

The earlier regression also passed before the final custom-domain metadata correction; the final focused run above includes that correction. Node SDK code and the separate provider-command contribution were not modified.

## Cleanup

No cloud resources were created. Provider tests use isolated local fixtures and temporary homes with cleanup. The companion CLI's real standalone/file-system probe is recorded at https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/40.

## Problems found

Capabilities are static declarations and cannot alone express account enablement, runtime/template/version conditions or implement missing APIs. Typed management registration is pending separate work at https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38 and https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/35. Registration requires a real handler and verified provider-bound routing. It is not full abstraction acceptance.

## Not verified

Live OpenSandbox and all catalog backends, unified conditional capability discovery, complete registry integration, newly published remote matrix/review, existing enabled-function/MicroVM acceptance, merge and release. ADR remains proposed; this record does not close the cross-repository task.
