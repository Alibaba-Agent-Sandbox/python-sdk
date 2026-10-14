# Built-in provider

`Sandbox.create()` with no `provider` uses `alicloud-express`. That id is the only provider compiled into the SDK.

`opensandbox`, `cubesandbox`, `e2b`, and `alicloud-container` are not in this package. Install one from the catalog, then pass its id:

```bash
python -m agent_sandbox.providers install registry:opensandbox --yes
```

Each provider's config, paths, and `E8004` list are in `awesome-providers/<id>/docs/README.md`. The CLI does not load those `python` plugins.

Express is the only provider that reads `ABX_SANDBOX_API_KEY`. None of the catalog providers read `E2B_*`.

## alicloud-express

Default. Credentials are `ABX_SANDBOX_API_KEY`, or `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`. Region is `ALIBABA_CLOUD_REGION_ID` (the CLI also stores it with `abx config set region`). Template images for this provider use the FC Dockerfile in `SKILL.md`.

Create goes through the local engine (`~/.abx/engine.sock`, or `ABX_ENGINE_SOCKET`). The engine holds the Express HTTP connection for that create. Commands and files on an existing Express sandbox use the envd URL from the create response.
