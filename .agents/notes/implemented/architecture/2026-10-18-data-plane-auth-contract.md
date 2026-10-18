# Decision: Require explicit sandbox API-key authentication
Status: implemented

## Problem

The default AK/SK fallback guesses a CreateApiKey RPC GET exchange, response
shape and one-hour expiry without a confirmed temporary-token service contract.
The official SDK instead models a credential-resource POST operation. A resource
creation method is not evidence for implicit token mint/refresh ownership.
Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/55.

## Decision

Remove the guessed default network exchange and its private signing/parser
helpers. The factory requires an explicit or canonical environment API key and
refuses AK/SK-only sandbox use locally. Preserve original factory arguments for
signature compatibility. Official CLI template/ACR control-plane clients remain
independent. Preserve exported AkSkAuth only for a caller-configured custom
exchange; require a non-empty string result and normalize it before caching.
The callback owner supplies its service contract, TTL and credential lifecycle.

## API Design

create_auth_provider(api_key, access_key_id, access_key_secret, *, region) keeps
its signature. AK/SK-only now raises InvalidAPIKeyError E1001 before I/O. API
key priority and provider-scoped credentials remain. Removed underscore-prefixed
exchange/signing imports are an intentional compatibility change, documented in
English and Chinese. No new endpoint, implicit resource or external service.

## Alternatives considered

- Change the guessed GET to official POST: could create persistent credentials
  repeatedly without consent, cleanup or a documented temporary-token TTL.
- Keep it as an experimental default: still selects unconfirmed behavior.
- Remove public custom adapter: unnecessary break for explicit integrations.

## Dependencies

CLI companion issue:
https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/52.
Official locked Node SDK @alicloud/fcsandbox20260509 1.5.1 was inspected:
CreateApiKey uses POST /pop/2026-05-09/api-keys, ROA/AK, and a structured
apiKey.apiKeyValue result. It is a real API; this record does not call it
nonexistent. No credential-resource method was executed.

## Test Strategy

Factory regressions assert AK/SK-only refusal without constructing HTTP clients,
canonical/explicit API-key precedence, custom callback cache/refresh and invalid
structured/empty results. Full package checks and configured real-cloud
create/use/kill acceptance must pass. Official control-plane code is unchanged;
companion CLI verifies its independent behavior.

## Acceptance criteria

- Default authentication never performs guessed credential exchange/creation.
- AK/SK-only failure is explicit, local and documented as a compatibility change.
- Valid direct/custom tokens work; malformed callback values never enter cache.
- Bilingual auth/config/troubleshooting/error guidance, changelog and evidence.
- Required full CI, real-component checks and review pass before merge.
