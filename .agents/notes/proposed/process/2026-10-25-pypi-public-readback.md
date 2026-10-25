# Decision: Bound PyPI public readback propagation retries
Status: proposed

## Problem

The first 0.4.0a2 publication uploaded both distributions but its fresh official-index
installation failed while the index still listed 0.4.0a1. Package JSON metadata had
previously returned temporary 404 responses. Retrying the failed job after propagation
passed with the same tag and immutable artifacts.

## Decision

Retry missing published metadata and fresh public installation at most six times,
ten seconds apart. Report every failed installation. Keep all four artifact filename
and SHA-256 comparisons, and immediately fail any verification error other than a
published metadata 404. Run pip check and public import checks once after installation.

## API Design

No product API, package version or publication tag changes. The existing release
checker returns temporary-failure status 75 only for published metadata HTTP 404;
preflight and digest checks keep their existing behavior.

## Alternatives considered

Unbounded retries hide failures. Retrying digest mismatches weakens immutability.
Parsing pip error messages to distinguish propagation is brittle and unnecessary
for a finite installation retry. A new publication framework is unnecessary.

## Dependencies

Official PyPI metadata/simple index and existing GitHub release artifacts.

## Test Strategy

Run the actual workflow shell with controlled external command results to test
recovery, exhaustion and hard failures. Independently compare the original release
artifacts with public PyPI and freshly install the exact public pair. Run SDK owner checks.

## Acceptance criteria

- Public installation tolerates bounded propagation delays without weakening hashes.
- Exhausted attempts, dependency errors and import errors fail the workflow.
- Original a2 release rerun and real public readback/install pass without replacing files.

## Evidence

- [Verification](../../../evidence/verify/2026-10-25-pypi-public-readback.md)
- [Issue 114](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/114)
