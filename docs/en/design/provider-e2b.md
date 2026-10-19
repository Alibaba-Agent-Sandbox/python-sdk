# E2B provider

E2B is a catalog provider. The source is `awesome-providers/e2b` and the id is `e2b`. Install with `abx provider install alibaba-agent-sandbox/awesome-providers//e2b --allow-unpinned --yes` (or `python -m agent_sandbox.providers install registry:e2b --yes`). `Sandbox.create(provider="e2b")` and `abx --provider e2b` talk to the public E2B API with the host's E2B protocol classes.

It is not compiled into the SDK. The manifest is `kind = "node"`: `provider.mjs` is loaded by the Node.js host, and the Python SDK reaches it through the local engine (`abx provider engine serve`). Its own notes are `awesome-providers/e2b/docs/README.md`.

The unit test does not call `https://api.e2b.dev`. It serves `POST /sandboxes` from a local TCP listener on `127.0.0.1`. A live call to E2B needs `ABX_ABX_SANDBOX_API_KEY`. Without it, `Sandbox.create(provider="e2b")` raises `InvalidAPIKeyError` before any request. The Express key is not sent to `api.e2b.dev`. This environment has no separate E2B key, so that live create did not run.

Chinese page: [provider-e2b.md](../../zh/design/provider-e2b.md).

## Configure

| Field | Type | Environment | Default |
|---|---|---|---|
| `base_url` | url | `ABX_E2B_BASE_URL` | `https://api.e2b.app` |
| `domain` | string | `ABX_ABX_SANDBOX_DOMAIN` | `e2b.app` |
| `api_key` | secret | `ABX_ABX_SANDBOX_API_KEY` | unset |

Pass the same three names in `provider_options`. `Sandbox.create(api_url=...)` does not select this origin. The resolver reads `provider_options["base_url"]`.

When the key is set, the client sends header `X-API-Key`. A missing `ABX_ABX_SANDBOX_API_KEY` raises `InvalidAPIKeyError` and the message names `ABX_ABX_SANDBOX_API_KEY`. This provider does not read `ABX_SANDBOX_API_KEY` (the Alibaba Cloud Express key) or retired `ABX_SANDBOX_API_KEY`.

`domain` is the suffix in `https://{port}-{sandboxID}.{domain}`. The envd port is 49983. A create response that omits `region` stays unknown (empty), not `cn-hangzhou`.

The current E2B SDK uses `https://api.e2b.app` and domain `e2b.app`. The data-plane host is `https://{port}-{sandboxID}.e2b.app`. `https://api.e2b.dev` is the older origin; set `ABX_E2B_BASE_URL` and `ABX_ABX_SANDBOX_DOMAIN` when an account still uses it.

```python
from agent_sandbox import ProviderSandbox as Sandbox

sb = await Sandbox.create(
    provider="e2b",
    provider_options={
        "base_url": "https://api.e2b.app",
        "domain": "e2b.app",
        "api_key": "...",
    },
    template="base",
)
```

## Features this adapter calls

Create is `POST /sandboxes` with `templateID`, `timeout`, `metadata`, and `envVars`. The shared protocol clients send the rest.

| Feature | What the shared protocol does |
|---|---|
| `sandbox.lifecycle` | `POST /sandboxes`, `GET /sandboxes`, `GET /sandboxes/{id}`, `DELETE /sandboxes/{id}`, `GET /v2/sandboxes` |
| `sandbox.timeout` | `POST /sandboxes/{id}/timeout` |
| `sandbox.pause` | `POST /sandboxes/{id}/pause` and `POST /sandboxes/{id}/resume` |
| `exec.run`, `exec.stream` | envd `POST /process.Process/Start` |
| `process.manage` | envd process list, stdin, and signals |
| `files.rw` | envd file read, write, list, move, and remove |
| `files.watch` | envd `WatchDir`. Declared, so it is not refused with `E8004` |
| `code.interpret` | envd `POST /code.CodeInterpreter/Execute` |
| `ports.url` | local `https://{port}-{sandboxID}.{domain}` |

## Calls that raise E8004

These ids are not in `features`. `feature_gate` refuses a protocol method whose feature is undeclared, before any HTTP request. `Provider.require` refuses the feature id the same way.

| Feature | What is refused |
|---|---|
| `pty` | interactive terminal. Public envd has no `/terminal` |
| `files.transfer` | signed or token file URL |
| `templates.read` | template list and get |
| `templates.build` | template build and publish |
| `ports.domain` | the separate domain-style feature id. Port hosts still use `domain` |
| `storage.mount` | volume mount |
| `network.vpc` | VPC |
| `sessions` | named commands on SandboxServer |

`files.watch` is declared. `files.watch` / `watch_dir` does not raise `E8004` for being undeclared.

## Extensions

`extensions` is empty. Nothing outside the 18 feature ids is registered.

E2B's public API also publishes endpoints this adapter does not call and does not register: sandbox logs (`GET /v2/sandboxes/{sandboxID}/logs`), metrics (`GET /sandboxes/{sandboxID}/metrics`), snapshots, fork, network update, volumes, template tags, team secrets, events, and webhooks. Volumes overlap the undeclared `storage.mount` feature. Template list and build overlap `templates.read` and `templates.build`.
