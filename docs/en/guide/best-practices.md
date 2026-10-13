# Best practices

How to run the in-sandbox server. Route shapes are in the [template server HTTP API](template-server-api.md). Path and command limits are in [File and command controls](file-and-command-controls.md).

## The server stays provider-free

`agent_sandbox.server` does not select a sandbox provider and does not read `--provider`. A template's `commands.py` imports only `agent_sandbox.server` and calls `start(9000)` under `if __name__ == "__main__"`.

Which `FROM` line, whether the Dockerfile may contain `CMD` or `ENTRYPOINT`, and the platform `start_cmd` live in the CLI provider profile (`abx-provider.toml` `[template]`, or the built-in `alicloud-express` constant). The HTTP routes do not change with that image. The client SDK does not pick the profile either.

## Turn on only the groups you need

The server has nine capability groups. `core` stays on (`GET /health`, `GET /capabilities`). These start enabled: `commands`, `file_ops`, `process`, `terminal`, `system`. These start disabled: `dev_tools`, `browser`, `agents`.

A group is only a name for the endpoints that declare it; the endpoint rule is the one switch. Turn a default group off in the template policy, as a map:

```yaml
server:
  groups:
    terminal: false
    process: false
```

`core` cannot be turned off. Turn an opt-in group on with a policy list (`groups: [dev_tools]`), with `default_table().enable_group(CapabilityGroup.DEV_TOOLS)` in `commands.py`, or with the environment variable `ABX_SERVER_ENABLED_GROUPS=dev_tools`. That variable only turns groups on; there is no variable that turns one off. `GET /capabilities` lists every endpoint with the `rule` that disabled it.

`shell`, `code_run`, and a PTY can run a program that reads any path the process can see. A path rule does not hold for an identity that also has those endpoints. For a template that only moves files, start from the `transfer-only` or `read-only` preset. See [File and command controls](file-and-command-controls.md).

## Leave `agents` off until a session needs it

The Agents routes stay off until the process is started with `ABX_SERVER_ENABLED_GROUPS=agents` (or `default_table().enable_group(CapabilityGroup.AGENTS)` in `commands.py`, or `groups: [agents]` in the policy). With the group off, those paths answer 404 with `code: endpoint_disabled` and the `rule` that decided (`default:opt-in:agents`).

Codex and Qwen Code are supported today. Checklist, the local header, and the 404s: [Hosted agents — Best practices](hosted-agents.md#best-practices).

## One agent by default

Install only the CLI you are going to call. Installing both Codex and Qwen Code makes the image large.

The server's order is `codex`, then `qwen-code`. A request that does not name an adapter uses the first. `GET /v1/agents/runtimes?order=asc` returns them in that order. The list's default `order` is `desc`. `default: true` marks the one in effect. It does not follow the array index.

```bash
npm install -g @openai/codex
```

To use Qwen Code, send `adapter`, `runtime`, or the `X-ABX-Adapter` header, or set `model` to `qwen-code` (aliases `qwen` and `qwencode`). A model id such as `gpt-5` is passed to the selected CLI. It does not switch the adapter.

Move the default off the first entry:

```bash
export ABX_AGENTS_DEFAULT=qwen-code
```

A JSON file named by `ABX_AGENTS_CONFIG` does the same with a top-level `default` or `agents.default`. `claude-code`, Cursor, and Qoder stay 404.

## Open Agents routes one endpoint at a time

`groups.agents: true` is only the gate for this group. Each Agents route has its own endpoint id, the same way `upload` and `shell` do. The default scope is `agents:use`. This opens session create and nothing else:

```python
from agent_sandbox.server import SandboxServer, ServerPolicy, default_table

policy = ServerPolicy.only("agents_sessions_create").with_options(groups={"agents": True})
server = SandboxServer(route_table=default_table(), policy=policy)
```

The same policy in YAML:

```yaml
groups:
  agents: true
endpoints:
  "*":
    enabled: false
  agents_sessions_create:
    enabled: true
```

These endpoints do not accept `paths` or specialised `params`. A policy that sets either fails to load. The full endpoint id list is in [Fine-grained capabilities](fine-grained-capabilities.md).

## Secrets are not echoed

`GET /env` omits a variable whose name contains `TOKEN`, `SECRET`, `KEY`, `PASSWORD`, or `CREDENTIAL`. When a policy is loaded it also omits `ABX_SERVER_TOKEN`, `ABX_SERVER_POLICY`, `ABX_SERVER_POLICY_FILE`, every `token_env` name, and every name that starts with `ABX_SERVER_`.

`POST /env` returns the names it updated (`{"updated": [...]}`), not the values. It refuses `PATH`, `HOME`, `USER`, `SHELL`, `ABX_SERVER_TOKEN`, and every `ABX_*` name. A policy can refuse more names with `params.allow_vars` / `params.deny_vars` on `env_get` and `env_set`.

A child process started while a policy with identities is active inherits the environment with those secret names removed. Passing one of them in a shell `env` object is `env_var_not_allowed`.

On the Agents routes, MCP header values come back as `"***"`. A vault credential's value, prefix, length, and hash are absent from responses, errors, and events.
