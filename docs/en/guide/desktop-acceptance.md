# Desktop interaction and simulated operator handover

This optional workflow uses `e2b_desktop.Sandbox` directly. It runs a real browser on a disposable Linux desktop, transfers control through a second noVNC client, and records an offline screenshot timeline. The operator in the acceptance test is simulated. It does not certify a real user's login or provide a hosted takeover service.

Prepare a private named template using the same-region official Desktop image `runtime/desktop:v0.0.44`, generation 2, 4 CPU and 8192 MB, and independently confirm `Ready`. The [official template guide](https://help.aliyun.com/zh/functioncompute/desktop-template-example) describes the image and build preparation. Preserve the actual template ID; the test never changes or deletes that caller-supplied template.

From this repository, install the isolated optional fixture and run it with your configured `E2B_API_KEY`, `E2B_API_URL` and `E2B_DOMAIN`:

```bash
uv venv --python 3.11 .venv-desktop
uv pip install --python .venv-desktop/bin/python -r e2e/desktop-requirements.txt
.venv-desktop/bin/python e2e/desktop_acceptance.py \
  --template "$E2B_DESKTOP_TEMPLATE" --output-dir ./desktop-evidence-new
```

A local Chromium executable must be available. Use `--browser-executable` when needed. The output directory must be new. This fixture is pinned to the tested desktop image, resolution and synthetic page; inspect the initial screenshot before adapting coordinates to another image.

## Three independent credentials

| Layer | Credential / header |
| --- | --- |
| SDK control API, commands and files | `envdAccessToken`, automatically carried as `X-Access-Token` |
| Private public-facing application port | `Sandbox.traffic_access_token`, carried as `e2b-traffic-access-token` |
| VNC session | Password created by `stream.start(require_auth=True)` |

Create with `secure=True` and `network={"allow_public_traffic": False}`. Keep the traffic token in the controlled backend proxy; the browser connects to its loopback endpoint. The [network access guide](https://help.aliyun.com/en/agent-sandbox/network-access-control) explains the separate control and ingress tokens. Inspect the actual negative and positive probes instead of treating a public HTML response or RFB banner as a successful authentication check.

The test checks screenshot PNGs, mouse and keyboard effects, wrong VNC password rejection, actual live WebSocket data, and the independently downloaded sequence `agent-start → operator-step → agent-resumed`. `replay.html`, `timeline.json`, screenshot SHA-256 values and `gui-state.json` preserve the run. Replay is a screenshot sequence, not a full-motion video recording. Only the newly created sandbox is deleted, with a separate typed not-found check. Delete your test template separately through its owning workflow.
