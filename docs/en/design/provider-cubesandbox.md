# CubeSandbox provider

CubeSandbox is a catalog provider. The source is `awesome-providers/cubesandbox` and the id is `cubesandbox`. Install with `abx provider install alibaba-agent-sandbox/awesome-providers//cubesandbox --allow-unpinned --yes` (or `python -m agent_sandbox.providers install registry:cubesandbox --yes`). `Sandbox.create(provider="cubesandbox")` and `abx --provider cubesandbox` talk to CubeAPI with the host's E2B protocol classes plus a few overrides in `provider.mjs`.

The manifest is `kind = "node"`: the Node.js host loads `provider.mjs`, and the Python SDK reaches it through the local engine (`abx provider engine serve`). Its own notes are `awesome-providers/cubesandbox/docs/README.md`.

The control-plane paths were read from [openapi.yml](https://github.com/TencentCloud/CubeSandbox/blob/master/openapi.yml) and the [Python SDK](https://github.com/TencentCloud/CubeSandbox/tree/master/sdk/python). The unit test does not need a live CubeSandbox. It serves `POST /sandboxes` from a local TCP listener on `127.0.0.1`. A live create needs CubeAPI listening on `127.0.0.1:3000`. The one-click installer stopped in preflight here: `/` is overlay, not the XFS filesystem `/data/cubelet` requires, and init is tini rather than systemd. Port 3000 was closed, so that live create did not run.

## Configure

| Field | Type | Environment | Default |
|---|---|---|---|
| `base_url` | url | `ABX_CUBESANDBOX_BASE_URL` | `http://127.0.0.1:3000` |
| `api_key` | secret, optional | `ABX_CUBESANDBOX_API_KEY` | unset |
| `domain` | string | `ABX_CUBESANDBOX_DOMAIN` | `cube.app` |

The default origin uses port 3000 because the Cube Python SDK README sets `CUBE_API_URL` to `http://127.0.0.1:3000`. Pass `provider_options={"base_url": "..."}` to override it. The value is the CubeAPI origin with no path prefix. Requests go to `/sandboxes`, not `/cubeapi/v1/sandboxes`.

When `api_key` is set, the client sends `X-API-Key`. When it is unset, the client sends no auth header. Local CubeAPI accepts that. This provider does not read `ABX_SANDBOX_API_KEY`. That variable is the Alibaba Cloud Express key.

`domain` is the suffix in port hosts `{port}-{sandboxID}.{domain}`.

```python
from agent_sandbox import ProviderSandbox as Sandbox

sb = await Sandbox.create(
    provider="cubesandbox",
    provider_options={
        "base_url": "http://127.0.0.1:3000",
        "api_key": "...",
        "domain": "cube.app",
    },
    template="base",
    timeout=60,
)
```

## Features this adapter calls

| Feature | HTTP the shared protocol sends | Confirmed on Cube |
|---|---|---|
| `sandbox.lifecycle` | `POST /sandboxes`, `GET /sandboxes`, `GET /sandboxes/{id}`, `DELETE /sandboxes/{id}`, `GET /v2/sandboxes` | OpenAPI and the SDK |
| `sandbox.timeout` | `POST /sandboxes/{id}/timeout` | OpenAPI and the SDK |
| `sandbox.pause` | `POST /sandboxes/{id}/pause` and `POST /sandboxes/{id}/resume` | OpenAPI and the SDK |
| `exec.run`, `exec.stream` | envd `POST /process.Process/Start` on port 49983 | Cube Python SDK |
| `files.rw` | envd `GET /files`, `POST /files`, and `POST /filesystem.Filesystem/{Stat,ListDir,MakeDir,Remove,Move}`. User defaults to `root` | Cube Python SDK |
| `files.watch` | envd `POST /filesystem.Filesystem/WatchDir` | Cube Python SDK `files.watch_dir` |
| `code.interpret` | envd Connect `POST /code.CodeInterpreter/Execute` | Not the Cube SDK path. See below |
| `ports.url` | local `{port}-{sandboxID}.{domain}` | Cube SDK `get_host` |

`connect` sends `POST /sandboxes/{id}/connect` first. That is how Cube resumes a paused sandbox. A 4xx falls back to `GET /sandboxes/{id}`. Process and file calls send `root` when the caller omits the user, because Cube envd rejects an empty user.

`run_code` posts to `http://49999-{id}.{domain}/execute` with `code`, `language`, and `env_vars`, and reads the ndjson response. Off the node, set `ABX_CUBESANDBOX_PROXY=host:80`. TCP dials that proxy and the Host header stays the virtual hostname.

## Calls that raise E8004

These are not in `features`. `feature_gate` refuses the protocol method before any HTTP request. `Provider.require` refuses the feature id the same way.

| Feature | What is refused |
|---|---|
| `files.transfer` | signed or token file URL |
| `pty` | interactive terminal |
| `templates.read`, `templates.build` | template list and build |
| `sessions` | named commands on SandboxServer |
| `process.manage` | process list, stdin, and signals. `exec.run` still starts a command |
| `ports.domain` | a separate domain-style feature id. Port hosts still use `domain` |
| `storage.mount` | the generic mount feature |
| `network.vpc` | VPC |

## Extensions

OpenAPI has three Cube-only capabilities that are not one of the 18 feature ids. They are registered with `implemented=False` and `when="sandbox"`. Nothing in this adapter calls them.

| Id | OpenAPI |
|---|---|
| `volume.mounts` | `NewSandbox.volumeMounts`, `/volumes` |
| `network.policy` | create body `network`, `PUT /sandboxes/{id}/network` |
| `distribution.scope` | `NewSandbox.distributionScope` |

`extensions_for` returns nothing until the caller passes a sandbox id. With a sandbox id, all three are visible because `when` is `sandbox`. `require_extension` on any of them raises `E8004` because `implemented` is false. `describe()["extensions"]` lists them even when no sandbox exists.

These OpenAPI operations also exist and are not registered, because they are not the three cube-only items above and this adapter does not call them: `GET /health`, `POST /sandboxes/{id}/refreshes`, `GET /sandboxes/{id}/logs`, `POST /sandboxes/{id}/snapshots`, `POST /sandboxes/{id}/rollback`, `GET /snapshots`, and the `/templates` build surface.
