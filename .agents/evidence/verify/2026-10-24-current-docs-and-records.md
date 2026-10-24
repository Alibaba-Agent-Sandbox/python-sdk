# Verification: current documentation and engineering records

- Date: 2026-10-24
- Result: PASS for local documentation checks; latest-head remote CI and review remain merge gates.
- Baseline: `04e8a716aa341ca2c15c48bc0bc94c3adf8d5848`.
- Scope: current Markdown documentation, lifecycle moves and owner index; no runtime or package change.

## Accepted note reconciliation

The GitHub API returned an actual merged timestamp and merge SHA for each linked PR:
- `2026-10-24-python-alpha-release`: [merged PR #91](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/91).
- `2026-10-23-template-workflow-contract`: [merged PR #89](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/89).

This updates the notes' lifecycle, not the historical observations in their evidence. Subsequent source preparation, release and runtime acceptance is linked from the current `.agents/README.md` entry. Older proposals outside this scope retain their original state where their full acceptance criteria have not been re-established.

## Validation

- PASS: `bash scripts/check-repo-health.sh`: 106 passes, one existing recommendation warning, zero failures; `make hygiene`; `git diff --check`.
- PASS: all 292 relative links in changed/new Markdown resolved locally; 12 Python blocks in the modified README/client/session pages parsed with `ast.parse`.
- PASS: a fresh environment installed public `agent-sandbox-client==0.3.1a5` and its matching server. Public imports and current ProviderSandbox method names were checked. The actual `LocalSessionStore` saved, loaded, listed and deleted a temporary record; temporary storage was removed.
- Independent review caught an incorrect draft inference that Python named sessions had been removed along with the CLI command. That draft was discarded: the final guide preserves the SDK feature, corrects the real `SessionManager` import and `list_sessions()` method, and distinguishes local metadata from remote snapshots and confirmed cleanup.
- The full process/file/server guide is retained. Only the obsolete installation claim, default-code-capability promise and unsupported Express interpreter example were replaced; the README uses explicit process execution and cleanup.

No new cloud resources or task credentials were created. Existing real-component receipts are references, not reruns under this documentation revision. The normal remote CI matrix remains mandatory; no runtime or publication workflow is weakened for this documentation change.

## Packaged skill follow-up

Independent review found the two current skills still instructed pre-release source-only installation, and their sample manifest/feature table contradicted the delivered workflow contract. Both now install public alpha 0.3.1a5, preserve standard versus Provider credentials, use an explicitly borrowed application binding, retain valid feature IDs and declare exact consumer operations. The SDK skill's source template uses spec 4; no unsupported host-kit interpreter is invented. Skill references were scanned for the same obsolete installation claims.

- PASS: the actual public-a5 `parse_manifest` accepts the complete REST example; `SandboxTemplate.model_validate` accepts the skill's source template. All skill Python blocks parse with `ast.parse`.
- Skill changes are instructions only. No image build, new cloud run, first Node package release or new Python package publication is claimed.
