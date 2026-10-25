# Decision: Match provider parameter help to the callable contract

Status: implemented

## Problem

Public a3 ProviderSandbox.create, connect, list and kill_by_id still document
removed api_key/api_url/domain parameters and alias-agreement behavior. Their
four generated synchronous wrappers copy those docstrings. kill_by_id also
lists sandbox_domain, which its control-plane signature does not accept.

## Decision

Describe only the actual sandbox_api_key and sandbox_base_url overrides, plus
sandbox_domain on create/connect/list. Remove nonexistent parameters and alias
claims. Keep every signature and executable provider statement unchanged.
Prepare lockstep client/server 0.4.0a4 for immutable package delivery; do not
recommend installing it before its successful official publication/readback.

## API Design

No new API, alias, fallback or schema. Standard Sandbox/AsyncSandbox ApiParams
retain their valid api_key/api_url/domain contract. get_info_by_id and
set_timeout_by_id keep their existing reference to the corrected kill_by_id help.

## Alternatives considered

Restoring aliases contradicts the current contract and the maintainer's request.
Overwriting public a3 artifacts is prohibited. A generic documentation framework
or broad parameter renaming is unnecessary for four source docstrings.

## Dependencies

- https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/124
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/123
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.4.0a3

## Test Strategy

Compare real installed public-a3 signatures/help against the candidate. Verify
all 12 lifecycle async/sync signatures are unchanged, document names are valid,
and 24 actual retired-keyword calls still reject before any provider/network
operation. Compare executable AST after excluding docstrings. Run the focused
regression, owner lint/type/tests/build/distribution checks and exact-head CI.
After review/merge, use the existing immutable release and official readback flow.

## Acceptance criteria

Four original docstrings and copied sync help match actual signatures; no runtime
contract changes. Bilingual configuration guidance and changelog are updated.
Owner checks, independent review and normal merge pass before publication. Public
artifact verification/fresh install receive new evidence; previous a3 evidence
and current installation claims remain accurate.

[Verification](../../../evidence/verify/2026-10-25-provider-parameter-docstrings.md).

## Implementation

PR 125 merged at 100da4661809f91a5d50e2722d1f4a8d4da3b131 after all 13 checks and independent review. Public a4 publication/readback completed; the first metadata-404 failure and successful same-tag retry are retained in the new public-a4 delivery evidence.
