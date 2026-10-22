# Python SDK development API

Use the provider extension through `ProviderSandbox` with `sandbox_api_key`, `sandbox_base_url` and `sandbox_domain`. SessionManager and the sandbox decorator use these same option names. Backend protocol implementations live in their owning provider packages; forwarding import modules have been removed.

Commands expose `send_input` and `send_signal`; files expose `stat` and `move`. Removed spellings have no forwarding methods. Provider port access is supplied explicitly by the selected provider.

The server client transfers files through `/files/upload-stream` and `/files/download-stream`. Authentication is evaluated by the policy token engine. Explicit policy tokens take precedence over the convenience `ABX_SERVER_TOKEN` setting. A remote standalone client supplies its PTY URL explicitly.

The pinned standard `Sandbox` and `AsyncSandbox` retain their upstream contract. See the [CLI development API](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/current-api.md) for template commands and configuration changes. Historical evidence describes its original revision only.

Configuration exports use one `storage` descriptor. Inert `max_retries` and `retry_base_delay` fields and the duplicate GlobalConfig model are removed; the retry utility remains an explicit opt-in helper. Secrets stored by the environment-file contract are not loaded from plaintext TOML.
