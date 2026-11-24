# Prepare a Provider runtime in Python

Use `agent_sandbox.providers.ProviderClient` from the Python SDK source to bind a Provider and a target at application startup. A compatible Python implementation supplied by the application or shipped with the SDK takes priority. Otherwise the client can fetch an approved standalone EPP implementation and its runtime. The SDK import and direct HTTP clients require no runtime preparation.

## OpenSandbox on Linux x86-64 with glibc

The [example lock](../../../examples/providers/locked-opensandbox/provider.lock.json) pins the Provider and Node.js archives, including their URLs, SHA-256 digests and byte lengths. Use a lock obtained through a distribution channel you trust. The OpenSandbox server must be reachable and able to start the selected image.

- Set `OPENSANDBOX_BASE_URL` to the OpenSandbox server URL.
- Set `OPENSANDBOX_API_KEY` if that server requires authentication. The key is sent to the Provider after local artifact verification.
- Optionally set `OPENSANDBOX_TEST_IMAGE` to an image the server can run.

The [example program](../../../examples/providers/locked-opensandbox/run.py) downloads the pinned assets, creates a sandbox, runs a command, checks file round-tripping, deletes the sandbox and confirms absence after a second preparation from the cache.

```bash
python examples/providers/locked-opensandbox/run.py
```

In an application, call `await ProviderClient.prepare(lock, config, cache_dir=path, download=True)` during a stage where network access is available. Reuse a private cache whose path and parent directories are controlled by the application operator. For offline preparation use the same cache and the default `download=False`. Cache entries are verified again on every preparation. If a cached digest fails verification, replace that cache entry using an approved copy or prepare into a fresh private cache.

## Use an installed Python Provider

Pass a trusted `Provider` instance as `native=`, or omit it to select a matching SDK-bundled implementation. For [Container Edition](../design/provider-alicloud-container.md), use `alicloud-container` and the installed SDK version in the lock, and pass the cluster options in `TransportConfig.provider_options`. Its ID and version must match `ProviderLock`. Declare the features you need using `required_features`. The SDK uses the compatible native implementation or selects an approved standalone entry for the host and feature set. Among standalone entries, Python is preferred, then the smallest numeric priority. You can supply a native-only lock without runtime entries. Install the Python implementation using your normal environment management.

`ProviderClient` provides `create(SandboxConfig(...))`, `connect`, `list`, `get`, `set_timeout` and `delete`. A client belongs to the event loop that prepared it. Close individual sandbox handles and close the client when finished. Call `delete` for owned sandboxes to release remote resources. `ProviderClient.close()` releases local resources.

Standalone preparation supports Linux glibc artifacts. Packages must provide a standalone EPP/1 entry. The example also requires a glibc version supported by the pinned Node distribution. Catalog installation and existing `ProviderSandbox.create(provider=...)` retain their own setup behavior. [Node.js platform requirements](https://github.com/nodejs/node/blob/v22.22.2/BUILDING.md)

If an operation loses its response after dispatch, inspect the returned error before retrying. A create error with `outcome == "unknown_outcome"` needs reconciliation. The optional `on_created` callback receives the ID as soon as the Provider returns it. Drain ongoing operations before closing a client.
