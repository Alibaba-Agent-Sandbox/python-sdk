# Decision: Read Python package inventory without requiring pip

Status: implemented

## Problem

[Issue184](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/184) was reproduced during SDK verification in a legitimate uv environment without pip. GET/packages?manager=pip ran python-m-pip, ignored its nonzero exit, and returned200 with an empty list despite installed distributions. Installing pip in the test environment did not repair that product behavior.

## Decision

Use standard-library importlib.metadata.distributions for the current interpreter's installed name/version metadata. Preserve response fields and the default manager identifier, stable case-insensitive name ordering, and no installation side effects. Skip entries without a name and deduplicate exact name/version pairs. Metadata enumeration failures return a sanitized500. The npm branch is unchanged.

## API Design

No new route, parameter or dependency. Existing200 manager/packages/name/version shape remains. The endpoint lists current Python distribution metadata; it is not a complete pip command wrapper or a cross-environment package manager.

## Alternatives considered

- Require users to install pip solely for observation: rejected because uv-only installations are valid.
- Hide command errors as an empty list: rejected because it misreports installed packages.
- Add a package installer or provider-specific inventory: outside this correction.

## Dependencies

Python standard library only. Independent review by the API/CLI agent confirmed the endpoint has no filters beyond manager and that current-interpreter metadata matches its public fields.

## Test Strategy

Actual installed pytest metadata with subprocess execution forbidden; malformed metadata produces sanitized error; duplicate/unnamed entries; a fresh uv-created environment without pip installed runs the real server and HTTP request.

## Acceptance criteria

Installed SDK and dependency distributions are listed without pip; response structure is unchanged; no new installer and no sensitive exception details.

## Evidence

- [Verification](../../../evidence/verify/2026-11-25-python-package-inventory.md)
