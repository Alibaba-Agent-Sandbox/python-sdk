# Build and deploy

The Python SDK is a runtime client. The CLI owns source acquisition, builds, deployment and source version publication. These are the current source commands; use `abx --help` for the installed release.

```bash
abx template init ./my-template --template python
abx deploy ./my-template --name my-app --yes
abx status my-app
```

Deployment handles source preparation. Keep the deployment name for status and deletion; no internal build or receipt file is needed for this flow. Before deleting it, connect from Python using the sandbox ID returned by deployment and follow [application connections](template-workflows.md) to call the registered `hello` function.

When the target has a bound OpenAPI contract, `abx sandbox my-app --help` lists its business operations and `abx sandbox my-app OPERATION --help` shows their arguments. Operation names come from that contract; registering a Python function alone does not create a CLI binding. See the [CLI API guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/sandbox-api.md).

For an existing native template, Python can call `await ProviderSandbox.create(template=template_id, provider=provider)`. Connect to the returned Sandbox ID when the CLI already started the application. `launch_template` is an advanced runtime entry: its caller must ensure that the image entrypoint or platform startup does not also start the manifest’s service.

After using the CLI-created deployment, delete it by name:

```bash
abx delete my-app --yes
```

[CLI authoring guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/authoring-templates.md) · [SDK application connections](template-workflows.md)
