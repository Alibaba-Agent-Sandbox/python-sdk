# Verification: real desktop, private stream and simulated operator handover

Result: PASS for the recorded GUI, private ingress, password-authenticated VNC, simulated operator handover and screenshot replay. Real human login, hosted takeover service and full-motion video recording remain NOT_RUN.

The optional fixture uses the official compatibility SDK `e2b-desktop==2.4.1` with `e2b==2.59.0`, Playwright 1.58.0, aiohttp 3.13.4 and the full exact dependency set in `e2e/desktop-requirements.txt`. It does not add desktop methods to the project client or MCP tool catalog. Python 3.11.15 and local Chromium 150.0.7871.114 were used. [Tested source hashes](2026-10-26-desktop-handover/tested-files.json) identify the exact permanent runner and fixtures.

## Real preparation and resource ownership

A unique test-owned generation-2 template was built through the actual official FC management SDK using the configured region's `fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/desktop:v0.0.44`, CPU 4 and memory 8192 MB. No startup/readiness command was invented, no existing template was changed, and no local Docker daemon was needed for this image-registration path. Independent template metadata showed `Ready`, generation 2 and the requested resources. [Build observations](2026-10-26-desktop-handover/build-state.json) preserve the actual progress.

The permanent source was then executed with a prepared template ID and a new output directory:

```bash
python e2e/desktop_acceptance.py --template TEST_OWNED_TEMPLATE_ID --output-dir NEW_EVIDENCE_DIRECTORY
```

The script created its own 600-second sandbox with `secure=True` and `network={"allow_public_traffic": False}`. Independent sandbox metadata confirmed 4 CPU / 8192 MB. The caller-supplied template was left for its separate owner to delete.

## Input, return and observed effect

| Action | Actual return / independent observation | Result |
| --- | --- | --- |
| Open a synthetic local application in real desktop Chrome | Actual 1024×768 PNG; browser page and editable form visible | PASS |
| Agent mouse focus, keyboard input and commit | Downloaded application state recorded `agent-start` | PASS |
| Enable private public-facing ports and inspect traffic token availability | SDK issued a nonempty `traffic_access_token`; no token was logged | PASS |
| HTTP/WS ingress without traffic token | HTML HTTP 403 and WebSocket HTTP 403 | PASS |
| Inject the correct traffic token in the backend proxy | HTML HTTP 200, actual live WebSocket data and rendered desktop canvas | PASS |
| Use the wrong VNC password after reaching the VNC service | Explicit password-check failure and no connected client | PASS |
| Connect with the correct VNC password | Actual rendered frames; 93,910 transferred bytes across the two VNC client probes by stream shutdown | PASS |
| Transfer input to a separate noVNC controller | Actual keyboard/mouse actions changed the independently downloaded state to `operator-step` | PASS simulated operator |
| Return input to the original SDK agent on the same desktop | Independently downloaded exact sequence `agent-start → operator-step → agent-resumed` | PASS |
| Stop stream and delete the test-owned sandbox | Stream stopped, delete succeeded, separate typed not-found query | PASS |
| Reopen offline replay in a real local browser | Initial, last and previous controls selected the expected actual frame files | PASS |

[Final machine-readable report](2026-10-26-desktop-handover/acceptance.json), [actual downloaded application state](2026-10-26-desktop-handover/gui-state.json), [timestamped screenshot hashes](2026-10-26-desktop-handover/timeline.json), [offline player](2026-10-26-desktop-handover/replay.html) and [portable replay archive](2026-10-26-desktop-handover/desktop-handover-replay.zip) preserve input-to-effect evidence. The [player check](2026-10-26-desktop-handover/replay-check.json) was a separate browser run. Six timeline entries include the diagnostic and final operator screenshot sharing the same content hash; this is not six independently different screens or a video recording.

## Authentication findings and preserved failed attempts

The successful private-ingress run kept three credentials separate:

- SDK control operations use `envdAccessToken` in `X-Access-Token`.
- Private application-port traffic uses `Sandbox.traffic_access_token` in `e2b-traffic-access-token`.
- The VNC session separately checks the password created by `stream.start(require_auth=True)`.

These are the [documented network layers](https://help.aliyun.com/en/agent-sandbox/network-access-control). The [official Desktop image guide](https://help.aliyun.com/zh/functioncompute/desktop-template-example) provides image and SDK preparation. The [Computer Use guide](https://help.aliyun.com/zh/functioncompute/use-the-computer-use-sandbox) describes GUI/stream actions; its abbreviated gateway paragraph must be read together with the actual network mode and ingress credential contract.

[Initial attempt reports](2026-10-26-desktop-handover/initial-attempts/) retain failures rather than replacing them with passes: the Chrome testing banner moved the initial coordinates; the connection configuration's public header accessor had to be used correctly; public-default HTML and an RFB banner were insufficient authentication evidence; the FC gateway added `Content-Disposition: attachment`; the first connected event preceded actual framebuffer delivery; and fast VNC shortcut/text entry did not fully apply. The final fixture used inspected screenshot coordinates, an appropriate MIME-preserving controlled proxy, actual frame checks and paced physical key events before independent state verification.

A separate [private run using the wrong token category](2026-10-26-desktop-handover/private-wrong-token-type.json) correctly returned 403 even with an envd token. The final run used the documented traffic token and returned 200. The earlier [public-default successful handover](2026-10-26-desktop-handover/public-default-handover.json) remains its own observation, not proof of private ingress enforcement.

## Checks and cleanup

- Scoped `ruff check e2e/desktop_acceptance.py` and `ruff format --check`: PASS.
- Permanent optional runner against the actual prepared cloud template: exit 0, all its assertions PASS.
- Real local-browser offline-player control check: PASS.
- Full SDK product checks are tracked by the coordinating acceptance task; no full-repository or remote CI success is claimed here.

All 11 exact test-created desktop sandbox IDs across exploratory and final runs were independently queried and returned typed not found: [cleanup observations](2026-10-26-desktop-handover/sandbox-cleanup.json). The unique owned desktop template's name was checked before deletion; a separate management `GetTemplate` returned HTTP 404: [template cleanup](2026-10-26-desktop-handover/template-cleanup.json). No borrowed sandbox, existing template or user account state was changed. The screenshot workflow used synthetic content and a simulated second controller; no actual user login was attempted.
