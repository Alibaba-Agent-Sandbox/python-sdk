# Reference providers

Provider plugins used by the test-suite and as templates for plugin authors.
Design: `docs/en/design/providers-and-credentials.md`; guide: `docs/en/guide/providers.md`.

| Directory | Kind | What it shows |
|---|---|---|
| `local-process/` | `exec` (EPP/1, Python stdlib, ~300 lines) | lifecycle, exec (buffered and streaming), files, scoped config fields (a secret and a bool), debug methods used by tests |
| `e2b-compatible/` | `rest` (manifest only, no code) | pointing the SDK/CLI at any E2B-protocol endpoint; consented `inherit` of the generic `sandbox_*` keys |

OpenSandbox is a catalog `python` provider in `awesome-providers/opensandbox`. HTTP stays in the plugin process:

```bash
python -m agent_sandbox.providers install registry:opensandbox --yes
```

```bash
python -m agent_sandbox.providers install examples/providers/local-process --yes
python -m agent_sandbox.providers list
```

```python
sb = await Sandbox.create(provider="local-process")
print((await sb.commands.run("echo hello")).stdout)
```

Nothing is executed at install time; the plugin only runs when a command uses it.
