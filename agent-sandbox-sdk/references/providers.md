This reference uses `from agent_sandbox import ProviderSandbox as Sandbox`. Root standard Sandbox/AsyncSandbox use the pinned E2B migration contract.

# Built-in provider

`Sandbox.create()` with no `provider` uses `alicloud-express`. That id is the only provider compiled into the SDK.

`opensandbox`, `cubesandbox`, `e2b`, and `alicloud-container` are not in this package. Install one from the catalog, then pass its id:

```bash
python -m agent_sandbox.providers install registry:opensandbox --yes
```

Each provider's config, paths, and `E8004` list are in `awesome-providers/<id>/docs/README.md`. All four are `runtime.kind = "node"` (an ES module, `provider.mjs`). There is no `python`-kind catalog plugin; a manifest with `kind = "python"` cannot be installed. An in-code `Provider` subclass still works from the SDK. Install with `abx provider install alibaba-agent-sandbox/awesome-providers//<id> --allow-unpinned --yes` or the Python module above, then `abx --provider <id>` or `Sandbox.create(provider="<id>")`. The Python SDK reaches a `node` provider through the local Node engine (`abx provider engine serve`, started on demand; `abx` must be on `PATH` or in `ABX_BIN`) using `EngineProvider`. Python `exec` and `rest` manifests still run in the Python process. The built-in `alicloud-express` is the Python builtin provider.

Native ProviderSandbox uses `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and `ABX_SANDBOX_DOMAIN`. The standard root entry separately maps E2B settings. Catalog providers keep their provider-specific credentials; never forward the Express key implicitly.

## alicloud-express

Default. Runtime credentials require `ABX_SANDBOX_API_KEY`. `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET` separately authorize official control-plane operations and cannot substitute for that runtime key. Region is `ALIBABA_CLOUD_REGION_ID` (the CLI also stores it with `abx config set region`). Template images for this provider use the FC Dockerfile in `SKILL.md`.

This reference describes ProviderSandbox, not the standard root Sandbox/AsyncSandbox. Use the configured provider transport rather than hardcoding engine sockets. Existing Express commands/files use the backend envd connection.
