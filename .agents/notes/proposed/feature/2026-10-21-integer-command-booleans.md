# Decision: Reject JSON booleans for integer named-command arguments

Status: proposed

## Problem
Python `int(True)` silently converts a JSON boolean into an integer before a named command can reject its input. Actual Express QM Sandbox acceptance exposed this behavior in the shared client/server parser. See [Issue 80](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/80).

## Decision
Reject Python bool values explicitly in the integer branch of both mirrored coercion modules, before dispatch. Preserve integer values, numeric strings, float coercion and boolean-typed arguments. HTTP conversion failure remains 400 TypeError.

## API Design
`parse_scalar(value, "integer")` raises ValueError for bool. `coerce_kwargs` preserves its existing TypeError wrapper. No new names or signatures. Callers sending JSON booleans to integer fields must send actual integers instead.

## Alternatives considered
- Change each template guard: conversion has already happened before the function is called.
- Relax template acceptance: would preserve the bypass and conceal the real observed defect.
- Make every scalar strict: unnecessary compatibility changes outside the reproduced integer/boolean defect.

## Dependencies
Repository health also indexes existing dated JSON evidence under `.agents/evidence/`; the old Markdown-only stem index produced six false missing-reference errors. [Issue 81](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/81) tracks this validation prerequisite. A temporary missing-record probe must still fail. Historical evidence stays unchanged.

No new dependencies. Server/client parser copies remain identical. Consumer work is [awesome-templates PR 171](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/pull/171).

## Test Strategy
First demonstrate failures in both bool parser cases and real local HTTP no-dispatch cases, then run both full package suites/lint/type checks and package verification. A dedicated real Express test uploads this checkout's complete server source, verifies raw HTTP and actual SDK rejection without dispatch, and retains valid integer/string/boolean behavior. Execute full cloud E2E and independently inspect owned cleanup.

## Acceptance criteria
The regression fails before the fix, all required checks and current-head review pass, actual cloud source validation and cleanup pass, bilingual protocol docs and changelog explain compatibility, and the owner PR is normally merged.

## Evidence
- [Verification](../../../evidence/verify/2026-10-21-integer-command-booleans.md)
