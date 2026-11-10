# Decision: Refresh the developer community QR code

Status: proposed

## Problem

The maintainer supplied a replacement DingTalk QR image on November 10 after the initial announcement.

## Decision

Replace the old PNG with the supplied 436 × 434 JPEG unchanged. Update both README image paths and clickable join URLs to the destination decoded from that image. Website shared UI owns the matching footer asset and URL; synchronize it to Registry. Keep the preview announcement, group name and group number unchanged.

## API Design

N/A — this decision does not involve API changes.

## Alternatives considered

Keeping the previous clickable URL would make clicking and scanning use different invitations. Converting or redrawing the supplied image is unnecessary; preserve its original bytes and file type.

## Dependencies

User attachment: https://api.agent.run/api/v1/uploads/up-x2G9-QN8rwuTx_0CKHcNkw.jpg . The shared UI source belongs to https://github.com/Alibaba-Agent-Sandbox/website .

## Test Strategy

Decode the replacement, compare asset bytes, validate bilingual image/link references, run owner document/build checks and inspect the rendered QR. Preserve all required remote CI gates.

## Acceptance criteria

The original replacement image is served, clicking and scanning use the same invitation, old image references are removed from current user-facing entry points, and affected source changes pass required checks before merge. Template PR303 retains its separately tracked CI blocker until resolved.

## Evidence

[Verification](../../../evidence/verify/2026-11-10-refresh-community-qr.md).
