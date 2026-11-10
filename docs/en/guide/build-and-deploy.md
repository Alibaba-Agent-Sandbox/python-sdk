# Build and deploy

The Python SDK is a runtime client. The CLI owns source acquisition, builds, deployment and source version publication. These are the current source commands; use `abx --help` for the installed release.

```bash
abx template init ./my-template --template python
abx deploy ./my-template --name my-app --yes
abx status my-app
abx sandbox command run my-app hello --arg name=Ada
abx delete my-app --yes
```

For reuse, prepare with `abx template build ./my-template --out ./.abx/build.json --yes`, then deploy with `abx deploy --build ./.abx/build.json --name my-app --yes`. Building creates no running instance. Deleting the application retains a separately prepared build. Clean an unused build with `abx template build --clean ./.abx/build.json --yes`; retained resources that require manual cleanup, such as images, are listed.

For an existing native template, Python can call `await ProviderSandbox.create(template=template_id, provider=provider)`. Connect to the returned Sandbox ID when the CLI already started the application. `launch_template` is an advanced runtime entry: its caller must ensure that the image entrypoint or platform startup does not also start the manifest’s service.

[CLI authoring guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/authoring-templates.md) · [SDK application connections](template-workflows.md)
