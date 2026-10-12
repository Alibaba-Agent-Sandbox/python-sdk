# Migrating from 0.2.x to 0.3.0

Version 0.3.0 splits the Python project into two lock-step PyPI distributions that share the
`easy_sandbox` import namespace:

| Distribution | Import | Contents |
|--------------|--------|----------|
| `easy-sandbox` | `easy_sandbox` | Client SDK (`Sandbox`, transport, protocol, templates API, `@sandbox`, MCP server, agents) |
| `easy-sandbox-server` | `easy_sandbox.server` | Container-side runtime that used to ship inside `easy-sandbox` |

`easy-sandbox` depends on `easy-sandbox-server==<same version>`, so a fresh
`pip install easy-sandbox` still provides both `from easy_sandbox import Sandbox` and
`from easy_sandbox.server import start`. Import paths do not change. The `[server]` extra
(`pip install "easy-sandbox[server]"`) is kept as a harmless alias.

Also removed in 0.3.0: the `[cli]` and `[binary]` extras and the `ebx` console script. Install the CLI
with `npm install -g @easy-sandbox/cli` (see the `cli` repository).

## In-place upgrade hazard

Upgrading an existing 0.2.x environment in place can leave `easy_sandbox.server` unusable:

```bash
pip install -U easy-sandbox
python -c "from easy_sandbox.server import start"
# ImportError: cannot import name 'start' from 'easy_sandbox.server' (unknown location)
```

Why: pip installs the new dependency `easy-sandbox-server` first, then uninstalls the old
`easy-sandbox` 0.2.x, whose file list still contains `easy_sandbox/server/*`. That removes the files
that were just installed, and `easy_sandbox.server` degrades to an empty namespace. A fresh
environment is not affected.

Fix it with either of these:

```bash
# Re-install only the server distribution, without touching its dependencies
pip install --force-reinstall --no-deps easy-sandbox-server

# or start clean
pip uninstall -y easy-sandbox easy-sandbox-server
pip install easy-sandbox
```

When the SDK detects this state (the `@sandbox` decorator's `sandbox.server` proxy and
`sandbox.register.upload()` / `.download()`), it raises an `ImportError` that names
`pip install easy-sandbox-server` and the `--force-reinstall --no-deps` remedy.

## Sandbox images and templates

Template images only need the container-side runtime, not the client stack. In a `Dockerfile` use:

```dockerfile
RUN pip3 install --no-cache-dir easy-sandbox-server
```

`ebx template deploy` / `DockerBuilder.inject_sdk_wheel` already injects the `easy-sandbox-server` wheel
(or falls back to `pip install easy-sandbox-server`). A server-only image has `easy_sandbox/server/`
but no `easy_sandbox/__init__.py`; `import easy_sandbox.server` works and `easy_sandbox.__version__`
is not defined there, so read `easy_sandbox.server.__version__` instead.

## Checklist

1. Pin `easy-sandbox>=0.3.0` and, in images, `easy-sandbox-server` (same version as the client).
2. Replace `pip install "easy-sandbox[cli]"` with `npm install -g @easy-sandbox/cli`.
3. If `import easy_sandbox.server` fails after upgrading, run the repair command above.
4. Use `easy_sandbox.server.__version__` (not `easy_sandbox.__version__`) inside containers.
