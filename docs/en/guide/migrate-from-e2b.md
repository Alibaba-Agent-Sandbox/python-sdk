# Migrating an Alibaba E2B application

The standard Python API targets `e2b==2.31.0` and `e2b-code-interpreter==2.8.1`, the versions recommended in [Alibaba's compatibility contract](https://help.aliyun.com/zh/agent-sandbox/e2b-compatibility-explanation). It owns its protocol implementation and installs neither E2B package. This contract applies to Alibaba Express; other providers use the explicit `ProviderSandbox` extension API. Node SDK migration is outside this change.

## Installation and imports

Install the published client with `python -m pip install --index-url https://pypi.org/simple agent-sandbox-client==0.4.0a2`. Configure the Express account with `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and `ABX_SANDBOX_DOMAIN`; these project settings work for standard `Sandbox` / `AsyncSandbox`, `code_interpreter` and `ProviderSandbox`. `abx config` and project/home configuration files also feed these settings. The standard client's public `api_key=` parameter remains part of its pinned contract. A separate application still using the third-party E2B SDK uses that SDK's native configuration names; do not send credentials from another provider account.


| Previous import | New import |
|---|---|
| `from e2b import Sandbox, AsyncSandbox` | `from agent_sandbox import Sandbox, AsyncSandbox` |
| `from e2b_code_interpreter import Sandbox, AsyncSandbox` | `from agent_sandbox.code_interpreter import Sandbox, AsyncSandbox` |
| `from e2b.exceptions import SandboxException` | `from agent_sandbox.exceptions import SandboxException` |

```python
from agent_sandbox.code_interpreter import Sandbox

sandbox = Sandbox.create(template="code-interpreter-v1", timeout=300)
try:
    sandbox.files.write("/tmp/input.txt", "hello")
    print(sandbox.commands.run("cat /tmp/input.txt").stdout)
    sandbox.run_code("value = 41")
    print(sandbox.run_code("value + 1").text)
finally:
    sandbox.kill()
```

`Sandbox` is synchronous; `AsyncSandbox` retains asynchronous methods. Do not add `await` to synchronous E2B code. `Sandbox.list()` returns a lazy paginator: use `has_next`, `next_items()` and `next_token`; the async paginator awaits `next_items()`. Class and instance lifecycle methods keep their E2B names (`Sandbox.kill(id)` and `sandbox.kill()`, likewise connect, get_info and set_timeout). Timeouts are seconds; `request_timeout=0` disables the request timeout. Nonzero commands raise `CommandExitException` with `exit_code`, `stdout`, `stderr`. Background execution returns a process handle with PID, wait, stdin and kill operations. File writes return `WriteInfo`; reads support text, bytes and streaming. Interpreter results, errors, callbacks and persistent code contexts retain their standard models.

## Capability boundary

| Capability | Contract / restriction |
|---|---|
| Lifecycle, queries, metadata filters, pagination, timeout, host and signed file URL generation | Standard API; URL usability still depends on backend envd authentication support, exactly as with the reference SDK |
| Commands, background processes, stdin, PTY, files and directory watch | Standard envd protocol and handle behavior |
| Interpreter, contexts, execution counts, stdout/stderr/result callbacks, multiple languages | Use `agent_sandbox.code_interpreter`; requires an interpreter-enabled template; charts must be saved to files on Alibaba |
| Templates, image-based builds | Standard Python Template API plus project CLI build/deploy extensions; actual backend permissions and build capabilities apply |
| Runtime network updates | Implemented (`update_network`), including allow/deny rules; `egress_proxy` has no effect on Alibaba; public traffic and host masking are creation-only settings |
| Pause/resume | Gen1 requires allowlist; Gen2 provides the capability, subject to actual function/account settings. The tested python-hello function rejected pause because pauseSession was not enabled |
| Snapshots | Implemented creation, lazy listing, deletion and restoration; MicroVM and allowlist required. Retention, qualified names, occupied snapshots and restore overrides follow [Alibaba's snapshot rules](https://help.aliyun.com/zh/agent-sandbox/snapshot-invited-test). Use `request_timeout=300`; preserve returned IDs/names |
| File metadata | Gen2/envd version dependent; older envd produces the same version error as the reference |
| Metrics/Logs | Alibaba docs have conflicting examples; no blanket availability promise. Service errors are preserved; console observability remains available |
| Volume, Team, API-key/access-token administration, MCP gateway | Outside Alibaba's supported E2B migration path. Exposed upstream types do not create missing service capabilities; manage these through supported cloud tools |
| OSS, VPC, Alibaba extensions | Provider/project extensions; not added to standard E2B arguments |

`ProviderSandbox` is the project's asynchronous provider/server/declarative extension API. Existing examples that use named server commands, sessions, custom providers or `sandbox.network` import it explicitly. These extensions are separate from the migration contract and are not alternate modes of `Sandbox`.

## Third-party integrations

Update imports in code you control, including wrappers and integration adapters. For a dependency that hardcodes `e2b` or checks E2B class identity, use its client factory/injection hook or maintain a small fork changing those imports; pin and test that adapter. Do not replace `sys.modules`, install a fake `e2b` package, or assume a string import rewrite changes runtime type checks. Private E2B internals and newer SDK versions are outside the pinned contract.

## Implementation provenance and verification

The protocol client is a maintained source port of the pinned MIT-licensed clients, relocated into the project namespace. Source hashes are in `client-sdk/src/agent_sandbox/_standard/SOURCES.json`; licenses accompany both source trees. There is no runtime E2B dependency. Contract regressions are in `client-sdk/tests/test_api/test_standard_contract.py`; real-cloud migration scenarios are in `e2e/test_standard_contract.py`. Passing interface tests does not imply every account has conditional cloud features enabled. See the engineering evidence for executed checks and limitations.

The optional snapshot `name` list filter is an Alibaba extension added beyond the pinned Python reference; existing signatures remain compatible. Qualified snapshot names are encoded in deletion paths.
