# Verification: capability declarations and frontend coverage

- Date: 2026-10-16
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/47
- Result: PARTIAL

The companion CLI review installed the real catalog OpenSandbox manifest into an isolated temporary HOME and confirmed sandbox.pause is advertised while the native provider CLI has no pause/resume command (exit 2 at parsing; no backend call). ProviderSandbox has pause/resume protocol methods. The Express CLI frontend and generic provider frontend are therefore not yet one complete operation surface. Typed registration alone does not fill that gap.

Corrected bilingual provider documentation that still claimed Express implements every host feature. The built-in adapter declares 15 features explicitly; generic storage.mount, network.vpc and ports.domain remain distinct pending integrations, not statements that the cloud lacks those services.

No backend request/resource creation occurred in this additional review. Real OpenSandbox E2E, generic CLI operation completion, condition discovery, provider-command integration and full acceptance remain unverified. SDK source did not change in this documentation correction. CLI owner: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/40.
