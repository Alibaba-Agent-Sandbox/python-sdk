# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |
| < 1.0   | :white_check_mark: |

## Reporting a Vulnerability

Agent Sandbox is an open-source project. **Please do NOT report security
vulnerabilities through public GitHub issues.**

Instead, report them privately by email:

📧 **liuyu@xmail.tech**

Alternatively, report privately through GitHub Security Advisories:

🔒 https://github.com/alibaba-agent-sandbox/python-sdk/security/advisories/new

This applies to all security issues in the Agent Sandbox Python packages
(`agent-sandbox-client` and `agent-sandbox-server`), the `abx` CLI (maintained in the
`agent-sandbox` repository, which follows the same private reporting process), and the
project's code.

### What to Include

When reporting a vulnerability, please include:

- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Any suggested fix (if applicable)

### Response Timeline

| Action | Timeframe |
|--------|-----------|
| Acknowledgment of report | Within **48 hours** |
| Initial assessment | Within **5 business days** |
| Fix development & testing | Within **30 days** (critical), **90 days** (non-critical) |
| Public disclosure | After fix is released |

### Process

1. You report the vulnerability via one of the private channels above (email or GitHub Security Advisories)
2. We acknowledge receipt and begin investigation
3. We work with you to understand and validate the issue
4. We develop and test a fix
5. We release the fix and publish a security advisory
6. We credit you in the advisory (unless you prefer anonymity)

## Security Best Practices for Users

- Keep `agent-sandbox-client` and `agent-sandbox-server` updated to the latest version (they are released in lockstep)
- Never commit API keys, tokens, or credentials to your repository
- Use environment variables or the SDK's keychain for authentication
- Review sandbox templates before deploying to production

## Scope

This security policy covers the Agent Sandbox project code: the `agent-sandbox-client`
and `agent-sandbox-server` Python packages, and the `abx` CLI (in the `agent-sandbox`
repository).

Thank you for helping keep Agent Sandbox and its users safe! 🔒
