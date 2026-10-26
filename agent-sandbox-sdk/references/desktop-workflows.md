# Desktop and browser interaction

Use the separately pinned optional `e2b_desktop.Sandbox` workflow in the [desktop acceptance guide](../../docs/en/guide/desktop-acceptance.md). Confirm the official image, same region, template readiness and actual resources before launching. Load `E2B_API_KEY`, `E2B_API_URL` and `E2B_DOMAIN` through local configuration; retain only the test-owned sandbox ID.

1. Create a disposable desktop with explicit lifetime, `secure=True` and `network={"allow_public_traffic": False}`. The verified fixture uses `runtime/desktop:v0.0.44`, 4 CPU, 8192 MB and 1024×768.
2. Capture and inspect the actual screenshot before mouse/keyboard actions. Chrome banners and window decorations can change coordinates. Independently query a resulting file or application state; an accepted key event does not prove the requested work happened.
3. Start the stream with `require_auth=True`. Keep `Sandbox.traffic_access_token` in a controlled backend and inject it as `e2b-traffic-access-token` on HTTP and WebSocket requests. `X-Access-Token` authenticates SDK control operations; the VNC password is a third credential. Verify absent/wrong credentials are rejected and the authorized stream actually renders frames.
4. Pause agent input before handing control to the authorized operator. Verify the operator's change through an independent application observation before returning control to the agent. State whether the operator was real or simulated; never claim a user login was tested using synthetic text.
5. Preserve timestamped actual screenshots, actions, hashes and delivered outputs. A screenshot timeline is not full-motion video. Stop the stream and delete only test-owned sandboxes; confirm absence independently. Borrowed desktops and caller-owned templates keep their original owner.

The reusable runner and fixed optional dependencies live in `e2e/desktop_acceptance.py` and `e2e/desktop-requirements.txt`. Its acceptance scope and raw results remain explicit; it does not add desktop methods to the project client or its MCP tool catalog.
