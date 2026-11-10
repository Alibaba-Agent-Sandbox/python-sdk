# Decision: Preview release notice and developer community

Status: proposed

## Problem

Readers need the maintainer's expected project 1.0.0 release date and one discoverable developer community contact.

## Decision

Update bilingual root READMEs and the original community QR image. State that Agent Sandbox is in preview, may introduce breaking changes, and is expected to release stable 1.0.0 on November 15, 2026. Keep the existing repository introduction and quick start. Use the supplied DingTalk group name, number 213605001586, join URL and unchanged QR image. This is a project announcement, not a package version change or a claim that release gates have passed.

## API Design

N/A — this decision does not involve API changes.

## Alternatives considered

A package version bump would incorrectly publish a future plan. An image-only contact would exclude readers who cannot scan it. An externally hosted upload would make the contact depend on the attachment service; keep the supplied image in the repository.

## Dependencies

The date and community details come from the maintainer's November 10 request. Shared UI is owned by https://github.com/Alibaba-Agent-Sandbox/website and synchronized to https://github.com/Alibaba-Agent-Sandbox/registry with its exact source manifest.

## Test Strategy

Check the changed document links, translations, image bytes and decoded destination. Run owner documentation gates; build and inspect both sites at desktop/mobile widths and both themes. Required remote CI/review and actual publication are separate from local validation.

## Acceptance criteria

The expected date, version, preview warning and community contact are visible in both README languages. New links and image paths resolve. No package/runtime version or existing user workflow changes. Site changes are bilingual, responsive and share identical UI sources. Merge only after applicable checks pass.

## Evidence

[Verification](../../../evidence/verify/2026-11-10-preview-release-community.md).
