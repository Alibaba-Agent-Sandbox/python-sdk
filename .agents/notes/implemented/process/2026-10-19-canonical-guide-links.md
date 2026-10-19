# Decision: Use verified canonical site links in active guides

Status: implemented

## Problem
Root README links were corrected, but bilingual documentation indexes and provider guides still send visitors to the older website or the unresolvable .com registry.

## Decision
Use the current canonical .cn website and registry in active guidance. Preserve historical design/archive evidence and all runtime endpoints.

## API Design
N/A — public documentation links only; configuration/API contracts do not change.

## Alternatives considered
Leaving only README correct still breaks guide navigation. Changing DNS or repository visibility is unnecessary and not authorized by this correction.

## Dependencies
Canonical www.agent-sandbox.cn and registry.agent-sandbox.cn were independently read HTTP200 during the release-readiness audit. Related consumer update: https://github.com/Alibaba-Agent-Sandbox/website/pull/13 .

## Test Strategy
Verify actual URLs, both language counterparts, hygiene/health and existing hosted documentation gates. No cloud/model test is needed for prose links.

## Acceptance criteria
Active documentation uses working canonical destinations, both languages match, owner evidence and current-head checks pass before merge. Later catalog aggregation reads the accepted source.
