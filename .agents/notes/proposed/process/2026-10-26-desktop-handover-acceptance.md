# Decision: verify optional desktop control through observable handover effects
Status: proposed

## Problem

A desktop feature claim needs actual screenshots, input effects, stream authentication, control transfer, replay and cleanup. A launch acknowledgement, public HTML or an RFB banner cannot establish those effects. A synthetic controller must not be reported as a real human login.

## Decision

Maintain a separate optional real-cloud compatibility fixture using the pinned official Desktop SDK and image. The fixture creates only its own sandbox, independently checks resources, drives a deterministic local application, transfers control to a separate VNC client, returns control to the original agent and downloads the resulting state. Record actual screenshot timestamps and hashes with an offline player. Enforce private public-facing ports using the traffic token, retain envd and VNC credential separation, and verify rejected and accepted access. Preserve initial failed attempts and exact cleanup evidence.

## API Design

No project client or MCP API changes. The optional runner accepts `--template`, `--output-dir` and `--browser-executable`; it refuses to overwrite evidence. Its caller-supplied template remains caller-owned. Optional fully pinned dependencies are isolated in `e2e/desktop-requirements.txt`.

## Alternatives considered

- Declare support from a provider feature or launch response: rejected because the requested observable work was not established.
- Treat public HTML or an RFB greeting as authenticated streaming: rejected; actual frames and independent application changes are required.
- Claim a full video or human acceptance from automated screenshots: rejected; the report explicitly labels the simulated operator and screenshot timeline.

## Dependencies

Official Desktop image `v0.0.44`, real same-region template/resources, `e2b-desktop==2.4.1`, `e2b==2.59.0`, Playwright 1.58.0, aiohttp 3.13.4 and the recorded full optional dependency set. A local Chromium executable is required before cloud creation.

## Implementation

New `e2e/desktop_acceptance.py`, exact optional requirements and two HTML fixtures; English/Chinese desktop acceptance guides; a linked `agent-sandbox-sdk/references/desktop-workflows.md` instruction. The proxy is a loopback acceptance fixture, not a hosted end-user authorization service. Public controls, private ingress and VNC passwords remain separate.

## Verification

[Real cloud evidence](../../../evidence/verify/2026-10-26-desktop-handover.md) records passing private HTTP/WS ingress tests, actual frames, wrong VNC password rejection, independent operator/agent state, actual screenshot playback and typed absence for all 11 test-owned desktop sandboxes. The single owned template was deleted and independently returned management HTTP 404. Scoped formatting/lint checks passed; complete SDK and remote gates remain separately recorded. The record stays proposed until accepted and merged.
