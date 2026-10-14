# SDK skill for coding agents

The skill in `agent-sandbox-sdk/` tells a coding agent how to write this SDK's code. It is a static guide. The SDK does not execute it.

Load it when the task is to write a client or a template (`template.yaml`, a Dockerfile, `commands.py`). Operating an existing sandbox with `abx` or MCP is the CLI skill in the `agent-sandbox` repository. Deploy, a local health check, and publishing the two packages are a short section at the end of the skill.

The guide covers:

- client code: `Sandbox.create`, `commands.run`, `run`, `files`, and the built-in provider `alicloud-express`
- a template: `template.yaml`, `Dockerfile`, `commands.py` with `@command` and `start()`
- deploy: `abx template deploy` (the Python package does not build images)
- test: `make test` and a local `commands.py` health check
- publish: one version for both packages, released from GitHub

The skill directory is [agent-sandbox-sdk](../../../agent-sandbox-sdk/SKILL.md). Copy that directory so `SKILL.md` sits in a folder named `agent-sandbox-sdk`. The `name` in the frontmatter matches that folder. Extra template notes live in `references/templates.md` beside it.

Writing a new provider plugin is a separate skill, [agent-sandbox-provider](../../../agent-sandbox-provider/SKILL.md).
