# Agents API — post-implementation protocol review, round 2

Date: 2026-11-17. Reviewer: protocol_audit.

Result: the reviewed candidate design is reasonable after the concrete corrections below;
**the user's complete delivered/released outcome is still NOT COMPLETE**. Image, cloud,
real six-Harness acceptance, runtime publication and SDK source-consumer migration are
separate unmet gates. This review does not approve treating local passes as those gates.

## Scope and independence

Reviewed root's corrected six-template generation/bootstrap/release/docs, the other
agent's native Harness adapters and authentication mapping, Registry/website topics,
new bilingual source article and the CLI's bilingual managed guide. My own Turn-wire
patch is not independently approved by this report: runtime_audit independently reviewed
it and the configured capability/identity tests. Changes remain candidate source at this
review; no package, remote merge or website deployment is inferred from local files.

## First-round findings rechecked

| Finding | Corrected behavior | Verification |
| --- | --- | --- |
| Missing modelEnvAllowlist | Bootstrap compiles the selected native names into the frozen runtime settings | Real bootstrap/config/Session/backend admission now reaches the intercepted infrastructure boundary for all six profiles |
| Literal plus markers in Docker RUN | Generator and all Guest install instructions are clean | Strict argv stand-ins execute exact shell; each injected old plus-marker control fails |
| All Harnesses described as Responses | Generated configuration text now uses each native protocol, Qoder native PAT/service and actual qoder binary | Source review of generator, profiles and generated bilingual instructions |
| Private/obsolete generator files | Closed shared-source list avoids ignored local overrides; check mode reports unexpected generated source | Generator implementation reviewed; --check passes |
| Same-name Turn/event fields | Stable frozen Agent identity, integer/null timestamps and host Turn in lifecycle event | Five local wire/capability tests pass, including official SDK local HTTP retrieval and SSE consumption |
| OpenCode completion records presented as live starts | Completion-only event kind emits terminal tool items, no synthetic running tool; per_tool_timeout=false | Parser/runtime/capability implementation and regressions reviewed |
| OpenCode workspace_write silently allowed full access | Adapter now rejects unsupported workspace_write and documents read_only/full_access; managed remains full_access inside Sandbox | Validate/build paths and bilingual Harness guide reviewed |
| Configured adapter reported installed | Runtime inventory reports configured=true and installed=null until a Guest can actually be inspected | Public API capability regression passes |

Independent executed commands in this round:

- `python scripts/sync_agents_api_templates.py --check`: PASS.
- `python scripts/test_agents_api_family.py`: three tests PASS, including six-profile
  native-admission flow and strict shell failure controls; no image/cloud claim.
- `pytest client-sdk/tests/test_managed_wire.py -q`: five PASS (1.48 seconds), including
  configured-runtime truthfulness and OpenAI3.52 typed/local-HTTP consumption.
- Scoped Ruff passed; final diff whitespace check passed. Owning repository full checks
  remain separately recorded by the coordinating agent.

## Protocol and native Harness conclusions

One project protocol for Sessions, submissions, turns/items, durable events, immutable
input/output files and cleanup is a reasonable common core. Native authentication is
selected explicitly; the host/standalone-server environment-name tables have parity
coverage. Credentials are not transported in command arguments or generated native
configuration files. Qoder does not receive an invented OpenAI endpoint. DSH's persistent
home and all three adapters' exact native-session flags preserve the intended continuation
mapping. This is a verified mapping/design, not six independent real-model resume passes.

Parser final outcomes are required. Empty zero exits cannot create successful Qoder,
OpenCode or DSH turns. OpenCode tool-call steps do not end a turn; explicit native errors
fail it. DSH committed text is not represented as token deltas. The runtime's process
observation and existing managed epoch/receipt uncertainty handling remain in place.
Local typed parsing of supported Turns/events does not establish full Session/Agent/error
schema parity with every OpenAI SDK. Functions, MCP result/approval flows, subagents,
mid-turn steering and automatic review remain absent from the public managed profile.

## Ingress review

The selected native FC custom-container topology is appropriate for the product's single
HTTP endpoint. The [official FC Web-function documentation](https://help.aliyun.com/en/functioncompute/web-functions)
distinguishes HTTP passthrough from API invocation, which becomes POST /invoke with an
application/octet-stream body and loses HTTP status/header information. The managed private
listener explicitly supports that media type and validates its signed role envelope; it
does not treat an API invocation status200 alone as business success.

The [official FC SSE documentation](https://help.aliyun.com/en/functioncompute/does-function-compute-support-sse-streaming-response)
requires a Web-function response carrying Transfer-Encoding:chunked. The Gateway emits
that header and chunk framing. No extra invented responseMode field is required by these
sources. Actual deployed URL routing, alias switching and live delivery must still be
observed on the provider; local chunk delivery and static props do not establish them.

## Topic and documentation review

Registry uses explicit six-Harness membership and ingested catalog availability. It does
not invent a successful runtime from source metadata. The old agents-api route redirects
to the topic. Registry links to the blog topic and template/API source; website links back
to the collection. The article starts with these usable entry links and uses real HTTP
clients; it does not invent a dedicated Gateway SDK.

The bilingual topic/article copy correctly separates the shared HTTP interface from
native capabilities and OpenAI's hosted architecture. It labels the six new templates as
under development, states the unsupported public workflows and the OpenCode per-tool
limit, and distinguishes old DeepSeek compatible-loop evidence from official DSH. The
old CSV article retains its fixed historical recipe and clearly bounds its Qwen result.
The English route can intentionally display that Chinese article via the website's actual
language-fallback implementation; this is not a broken invented English source article.

Visually inspected the captured Registry Chinese desktop light screenshot and website
English mobile dark screenshot. Both show the intended shared container and clear topic
entry, readable stacked mobile content, consistent article rows and explicit language
badges for fallback posts. These two manual checks are not a claim that every screenshot
or interaction was manually reviewed. The recorded browser matrix separately reports
routes/layout/errors and does not represent model or cloud acceptance.

CLI guidance points to the source-owned family and preserves application-owned database,
credential, publication and drain responsibilities. Its candidate-version warning avoids
claiming released older packages support the new YAML/adapters. No new CLI command tree
or unrelated package release was introduced for these documentation links.

## SDK YAML consumer boundary

Actual call tracing established a remaining earlier-task gap: the packaged Python YAML
normalizer/discovery and launch_template still consume the older single-Sandbox draft,
while current templates and CLI use named resources. The current template run.py uses
ProviderSandbox.create/start_server directly; managed ExpressBackend and the JavaScript
CLI do not call that older Python source parser. It therefore does not block the corrected
managed-template runtime path.

The owner-approved scoped response corrects AGENTS.md and eight bilingual documentation
pairs, preserves useful independent runtime APIs and records the unmigrated source
consumer honestly. It does not pretend schema-byte sync alone is a migration, silently
remove SDK APIs or grow another deployment engine. The overall YAML owner Issue309 must
stay open until its actual remaining consumer criteria are delivered or explicitly
resolved by the owner.

## Remaining delivery gates

- Matching client/server0.4.0a8 is still an unpublished candidate at this review. The
  template's pinned image installs are blocked until real paired artifacts exist.
- All six changed images need exact-source build and native installation evidence.
- FC Gateway/Worker/Dispatcher with actual PostgreSQL, native model tasks, per-Session
  continuation, retained-session upgrade, cancellation and independently confirmed owned
  cleanup must be completed within the stated scope. Local fixtures and prior recipe
  results cannot stand in for this candidate.
- Existing raw-socket regression failures remain failures. The stdlib-only control
  reproduced the raw501/timeout distinction outside project imports while normal HTTP
  clients passed. It does not justify weakening tests or claiming an unrun remote matrix.
- Latest-head CI, required reviews, actual PR merges, package publication/readback and
  public site deploy verification must be checked independently before claiming release.

There is no remaining observed blocker in the reviewed corrected local template/core
contract mapping, but this is **conditional readiness for the next delivery gates**, not
completion of the user's end-to-end request or approval to close the cross-repository Issue.
