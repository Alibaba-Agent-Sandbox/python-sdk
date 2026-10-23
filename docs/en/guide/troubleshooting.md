# Troubleshooting (FAQ)

For current SDK installation, use the [paired source installation guide](install-python.md).

> **Note:** The `abx` commands shown on this page are provided by the Node.js CLI in the `cli` repository ([CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md)). CLI-specific documentation (CLI design, tutorial, reference) lives there too; this repository documents the Python SDK (`agent-sandbox-client`) and the container-side runtime (`agent-sandbox-server`).

---

## Connection Timeout

### Symptoms

```text
[E5001] Failed to connect to sandbox service
  Suggestion: Check network connectivity and firewall rules.
```

### Troubleshooting

1. **Check network**: Confirm you can access `api.cn-hangzhou.e2b.fc.aliyuncs.com`
   ```bash
   curl -I https://api.cn-hangzhou.e2b.fc.aliyuncs.com
   ```

2. **Check timeout configuration**: Increase the HTTP timeout
   ```bash
   abx config set http_timeout 60
   ```

3. **Check proxy**: If behind a proxy, ensure `https_proxy` is configured correctly

4. **Check region**: Confirm the region setting is correct
   ```bash
   abx config get region
   ```

---

## Authentication Failure

### E1001 — Invalid or Missing API Key

```text
[E1001] API key cannot be empty
  Suggestion: Check your E2B_API_KEY environment variable or pass sandbox_api_key.
```

**Solution**:
```bash
# Check configuration status
abx config get sandbox_api_key

# Re-set API Key
abx config set sandbox_api_key your-api-key

# Or set the environment variable
export E2B_API_KEY="your-api-key"
```

### E1003 — Invalid AK/SK Credentials

```text
[E1003] AccessKey ID and Secret cannot be empty
```

**Solution**: Ensure both AK ID and AK Secret are set:
```bash
export ALICLOUD_ACCESS_KEY_ID="your-ak-id"
export ALICLOUD_ACCESS_KEY_SECRET="your-ak-secret"
```

### E1002 — Token Expired

```text
[E1002] envdAccessToken not available. Sandbox may not be created or connected.
```

**Solution**: Check that the system clock is accurate. Reconnect for a current envd token or inspect an explicitly configured custom exchange; API keys are not automatically minted or refreshed.

---

## Template Not Found

### E2001 — TemplateNotFoundError

```text
[E2001] Template 'my-template' not found
  Suggestion: Run 'abx template list' to see available templates.
```

**Solution**:

1. Check the template name for typos
2. Confirm the template is installed:
   ```bash
   abx template install owner/repo
   ```
3. Test with the default template:
   ```bash
   abx create base
   ```

### E2009 — SandboxNotFoundError

```text
[E2009] Sandbox 'sbx-xxxx' was not found.
```

The platform answered HTTP 404 to `Sandbox.connect()`, `get_info()`, `set_timeout()`, `pause()` or `resume()` for that ID.

**Solution**: Check the ID for typos and run `abx list` to see the running sandboxes. A killed or expired sandbox cannot be reconnected; create a new one. `kill()` of an unknown ID stays idempotent and does not raise.

---

## Capability Not Supported (E3004)

### Symptoms

A selected catalog path has unmet requirements, or E8004 names an exact operation such as `code.execute` or `code.context.execute`. A server policy-disabled endpoint can instead return `endpoint_disabled` / E9003 (also E3004).

### Explanation

Template software, the project provider adapter, the selected client and the current instance environment are distinct layers. Missing project adapter support does not prove a native platform API is missing. A missing unified interpreter operation does not block unrelated application HTTP. Beta maturity and current path evidence remain separate.

### Solution

1. Identify the workflow, consumer and owner of the failed condition. Use a [spec4 manifest](../reference/template-yaml-spec.md); adding retired `capabilities` or `tested_on` is invalid.
2. Implement/install the missing adapter operation or explicitly choose an implemented workflow. Stateless, default persistent context, explicit contexts and realtime streams are different operations.
3. For an application, resolve the endpoint independently with `async with await sandbox.application_client(9000, token=application_token)`. Check the listening process, protocol version, gateway configuration and application token.
4. HTTP 401 never retries anonymously; interpreter HTTP 404 never becomes shell execution. Use the commands API explicitly when shell is intended.
5. Server policy separately controls nine endpoint groups. `core` stays on; `dev_tools`, `browser` and `agents` start off. Check the actual loaded policy, `server:` and environment, not retired template flags.

See [explicit template workflows](template-workflows.md) and [Template server HTTP API](template-server-api.md).

---

## Quota Exceeded

### E2002 — QuotaExceededError

```text
[E2002] Sandbox quota has been exceeded
  Suggestion: Destroy idle sandboxes or request a quota increase.
```

**Solution**:

```bash
# View running sandboxes
abx list --status running

# Destroy unneeded sandboxes
abx kill sbx-xxxx

# Batch destroy
abx kill --all --yes
```

---

## Command Execution Timeout

### E3001 — CommandTimeoutError

```text
[E3001] Command execution timed out
  Suggestion: Increase the timeout parameter or check if the command is hanging.
```

**Solution**:

```python
# Increase timeout in SDK
result = await sandbox.commands.run("long-command", timeout=300)

# Increase timeout in CLI
abx exec sbx-xxxx "long-command" --timeout 300
```

---

## Build and Deploy Issues

Build, push and deploy errors (the `E7xxx` codes, a missing LLM key for `abx create` / `abx template scaffold`) are raised by the `abx` CLI, not by this SDK. See the CLI troubleshooting guide and [Build and deploy](build-and-deploy.md).

---

## File Operations

### E4001 — File Not Found

```python
# Check if the file exists first
exists = await sandbox.files.exists("/path/to/file")
if not exists:
    print("File does not exist")

# List directory contents
entries = await sandbox.files.list("/home/user")
```

### E4002 — Permission Denied

Check file permissions. The default user in the sandbox is `user`; you can specify the `user` parameter in commands.

---

## Installation Issues

### pip install Fails

```bash
# Ensure the correct package name
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/c8882c29fd6a84fe10f9e6791aeacd1f5c0a5131.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/c8882c29fd6a84fe10f9e6791aeacd1f5c0a5131.tar.gz#subdirectory=client-sdk"

# If dependency conflicts occur
python -m pip check
```

### Python SDK Not Found

Confirm that Python's bin directory is in your PATH:

```bash
python -c "from importlib.metadata import version; print(version('agent-sandbox-client'))"
# Or
python -m pip show agent-sandbox-client
```

---

## Next Steps

- [Authentication](authentication.md) — Authentication configuration
- [Configuration Reference](../reference/configuration.md) — All configuration options
- [Error Codes Reference](../reference/error-codes.md) — Complete error code list

---

## Related: the abx CLI

CLI-specific problems (`abx` not found, `abx deploy` with no Dockerfile, long deploy steps, invalid shortcut targets, `abx template scaffold --adopt` confirmations) are covered in the CLI repository: [Troubleshooting (CLI)](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/troubleshooting.md).
