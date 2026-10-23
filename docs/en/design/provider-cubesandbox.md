# CubeSandbox provider

CubeSandbox is a catalog Provider consumed by the CLI and Python `ProviderSandbox` through the local engine. The Node.js server HTTP client is a separate consumer and does not manage cloud sandboxes. [中文](../../zh/design/provider-cubesandbox.md).

The authoritative plugin and operation declarations live in [awesome-providers/cubesandbox](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/tree/main/cubesandbox). Install its Git tree with `abx provider install alibaba-agent-sandbox/awesome-providers//cubesandbox --allow-unpinned --yes`, or use the Python registry installer `python -m agent_sandbox.providers install registry:cubesandbox --yes`. Pin a reviewed full commit for reproducible use.

## Exact interpreter boundary

The adapter implements only `code.default-context.execute`: persistent variables in a sandbox's default Jupyter context. It sends JSON `code`, `language` and optional `env_vars` to `/execute` on port 49999 and reads the buffered NDJSON result. Call `await sandbox.run_code("x = 42", mode="default-context")` explicitly.

Stateless `code.execute`, explicit context create/execute/list/restart/delete, realtime `code.stream` and `code.results.structured` are not declared. Context IDs and callbacks are rejected before code I/O. A buffered result does not promise realtime callbacks, and missing interpreter services do not fall back to a shell.

This mapping is distinct from the removed guessed Connect interpreter RPC. Cube's [official Python SDK README](https://github.com/TencentCloud/CubeSandbox/blob/master/sdk/python/README.md) documents `/execute` and persistent variables. This source mapping and loopback tests do not establish a live Cube deployment pass.

## Configure and create

| Field | Environment | Default |
| --- | --- | --- |
| API origin | `ABX_CUBESANDBOX_BASE_URL` | `http://127.0.0.1:3000` |
| Optional provider key | `ABX_CUBESANDBOX_API_KEY` | Unset |
| Port-host suffix | `ABX_CUBESANDBOX_DOMAIN` | `cube.app` |
| Remote node proxy | `ABX_CUBESANDBOX_PROXY` | Unset |

Provider-scoped keys stay separate from Express credentials. Process and filesystem calls use envd on port 49983; Jupyter uses 49999. Port hosts are `{port}-{sandboxID}.{domain}`. The adapter's optional proxy controls TCP dialing while retaining the virtual Host name.

```python
from agent_sandbox import ProviderSandbox

sandbox = await ProviderSandbox.create(
    provider="cubesandbox",
    template="YOUR_NATIVE_TEMPLATE_ID",
    provider_options={"base_url": "http://127.0.0.1:3000", "domain": "cube.app"},
    timeout=60,
)
try:
    result = await sandbox.run_code("print(42)", mode="default-context")
finally:
    await sandbox.kill()
```

The control-plane mapping follows the [Cube OpenAPI](https://github.com/TencentCloud/CubeSandbox/blob/master/openapi.yml) and [official SDK](https://github.com/TencentCloud/CubeSandbox/tree/master/sdk/python). The plugin maps lifecycle/timeout/pause/resume, exec, files and ports independently. Its manifest is the current operation authority; coarse feature groups do not authorize another workflow. Process management, PTY, file transfer, native template inventory, storage and VPC are not inferred from another supported operation.

## Source preparation and evidence

CLI source preparation requires an explicit compatible Dockerfile/profile, Docker, a writable image repository and native Cube registration prerequisites. It preserves FROM, USER, COPY and ENTRYPOINT. It returns the same provider's native managed reference; raw OCI references are not treated as Cube template IDs. Python does not declare `template.prepare` and consumes an already prepared reference.

Cube remains Beta. Unit/loopback tests exercise mapping and failure behavior; native create requires an actual CubeAPI, valid native template and node/runtime setup. This environment has not completed that native acceptance. New source or binding identities require new scoped evidence; a historical record cannot certify the current workflow.
