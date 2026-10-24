# OpenSandbox provider

OpenSandbox is a catalog Node provider owned by [awesome-providers/opensandbox](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox). The Python `ProviderSandbox` reaches that adapter through the local CLI engine; an engine transport URL is not the application's HTTP URL. The platform, adapter, template and consuming client are separate layers.

## Current adapter (2026-10-23)

The adapter manifest declares operation contract 1, exact operations for CLI and Python, and supported workflow inputs/startup modes. Its broad feature metadata describes management/discovery; it does not grant an interpreter or certify a template. The installed code and manifest must agree. Consult the [plugin's current manifest](https://github.com/alibaba-agent-sandbox/awesome-providers/blob/main/opensandbox/abx-provider.toml) and [workflow guide](../guide/template-workflows.md), rather than copying a historical feature matrix.

Configure the plugin with its own OpenSandbox base URL and API key. The Express API key is not an OpenSandbox credential. Installation/configuration instructions and Docker acceptance commands are maintained in the plugin's English/Chinese README. Node 22 is required by the catalog engine and WebSocket implementation.

## Template and interpreter relationships

A template may supply Python, Jupyter or an HTTP application. Those contents do not implement a project SDK protocol bridge. In the current project adapter, unified interpreter operations are not implemented. A refusal for `code.execute` or a context operation means this adapter/client path cannot invoke it; it does not prove OpenSandbox's native API lacks that capability. An interpreter image name alone never grants an operation.

Application HTTP is independent. A source application uses its declared build profile, startup mode, port/protocol and operation. A prepared image workflow uses an immutable image digest. A service workflow uses an explicit application URL. Each selected path is planned against the exact operations of the chosen consumer. Missing interpreter support does not block an unrelated application workflow.

Shell execution remains an explicit `exec.run`/`exec.stream` path. Missing interpreter routes are never silently converted into a temporary Python script or shell command. Historical Express interpreter-to-shell substitution has been deleted from current project adapters; the independently pinned standard clients keep their own contract.

## Application endpoint binding

The adapter returns the actual sandbox port endpoint with provider ID, sandbox ID, port, gateway authentication audience, path mode, headers and optional expiry. The Python consumer obtains this through `await sandbox.application_client(port, token=application_token)`. The gateway credential and application token are different identities. Proxy prefixes and opaque signed query values are preserved. Redirects, namespace traversal and ambiguous authority/query overrides fail before payload.

`engine://opensandbox/<id>` remains an internal transport identifier. It is not rewritten into an HTTP application address by guessing a host or route. Operation-signed endpoints require an explicit operation resolver; they cannot be blindly joined as prefix URLs.

## Verification scope

Static T/F/U planning, provider maturity, visitor environment and actual deployment evidence are distinct. T permits local checks; the account, network and running application remain unchecked until execution. A historical native OpenSandbox Stable result does not verify a new CLI/Python workflow. Author PASS JSON is not project certification.

The Provider repository owns Docker-backed T4 checks for plugin lifecycle/files, installed SDK integration and the portable application workflow. An acceptance record must name exact source/manifest/provider/consumer/workflow/binding identities, required checks and cleanup. Only independently approved CI provenance can qualify a catalog receipt. See [template workflows](../guide/template-workflows.md).

## Historical research

The earlier exec-plugin research is retained in [the archive](../archive/provider-opensandbox-research.md). Historical feature tables, image-name inference and shell substitution are not the current contract. Current implementation and verification evidence belong to the owning repositories.
