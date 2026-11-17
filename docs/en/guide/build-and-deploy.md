# Build and deploy

The Python SDK is a runtime client. The CLI owns source acquisition, builds, deployment and source version publication. These are the current source commands; use `abx --help` for the installed release.

```bash
abx template init ./my-template --template python
abx deploy ./my-template --name my-app --yes
abx status my-app
abx delete my-app --yes
```

For reuse, prepare with `abx template build ./my-template --out ./.abx/build.json --yes`, then deploy with `abx deploy --build ./.abx/build.json --name my-app --yes`. Building creates no running instance. Deleting the application retains a separately prepared build. Clean an unused build with `abx template build --clean ./.abx/build.json --yes`; retained resources that require manual cleanup, such as images, are listed.

For a Sandbox resource, deployment returns a reusable template ID. Follow the selected template's `run.py` instructions to create and start a dynamic instance, or use `await ProviderSandbox.create(template=template_id, provider=provider)` and explicitly start its application. Connect to that returned Sandbox ID for later calls and close/delete it before removing prepared resources. The SDK's older `launch_template` snapshot interface does not accept current named-resource source files; see the linked runtime guide.

[CLI authoring guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/authoring-templates.md) · [SDK application connections](template-workflows.md)
