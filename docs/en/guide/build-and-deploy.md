# Build and Deploy (SDK)

The Python SDK offers two ways to build and deploy sandbox images from code: the **in-sandbox agent deploy**
(`Sandbox.deploy()`) and the **`Image` chained build**.

> Publishing a template from the command line (`ebx template init` → `ebx deploy` → `ebx create`) is a CLI workflow,
> described in the CLI's [Deploy and Build](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/deploy-and-build.md) guide.

---

## Sandbox.deploy (SDK only)

`Sandbox.deploy()` starts a `qwen-code` template sandbox, uploads the project and lets the in-sandbox agent analyze, install, build and start the service. It is available as a Python API only.

The agent:
1. Creates a sandbox with the `qwen-code` template (default 2 CPU / 4096MB memory)
2. Uploads the project directory
3. Analyzes the project structure and dependencies
4. Installs dependencies and builds
5. Starts the service

### Usage

```python
from easy_sandbox.api.sandbox import Sandbox

sandbox = await Sandbox.deploy(
    project_path="./my-flask-app",
    description="Deploy this Flask app on port 8080",
    max_wall_time="10m",         # Max agent runtime (default 10m)
    max_session_turns=100,       # Max qwen-code session turns (default 100)
    timeout=900,                 # Sandbox timeout in seconds (default 900)
    cpu=2,                       # CPU cores (default 2)
    memory=4096,                 # Memory in MB (default 4096)
    on_progress=lambda msg: print(f"[Progress] {msg}"),
)

# The sandbox is still running; you can continue operating on it
print(f"Sandbox ID: {sandbox.id}")
print(f"Deploy result: {sandbox._deploy_result}")
```

### LLM Key Configuration

`Sandbox.deploy()` (not `ebx deploy`) requires an LLM API key. The SDK looks for one in this order:

1. `llm_api_key=` argument
2. Process environment: `EBX_LLM_API_KEY`, then `BAILIAN_CODING_PLAN_API_KEY`, `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`, then a legacy `EBX_QWEN_CODE_API_KEY`
3. The same names in `./.env`
4. `EBX_LLM_API_KEY` saved by `ebx config set llm_api_key` (`~/.ebx/.env`)

Base URL and model follow the same layers (`openai_base_url=` / `openai_model=`, then `EBX_LLM_BASE_URL` / `OPENAI_BASE_URL` and `EBX_LLM_MODEL` / `OPENAI_MODEL`, then the same names in `./.env`, then `~/.ebx/config.toml`). A blank value does not count. The full table is in [Credential resolution](../reference/configuration.md#credential-resolution).

If no key is found, `DeployLLMKeyMissingError` (E7001) is raised. `ebx deploy` never raises it.

---

## Image Chained API

The `Image` class provides a Modal-like chained API for declarative Docker image building.

### Basic Usage

```python
from easy_sandbox.api.image import Image

image = (
    Image.from_template("python-base")
    .pip_install("flask", "sqlalchemy")
    .apt_install("postgresql-client")
    .env(DATABASE_URL="postgresql://localhost/mydb")
    .run_command("echo 'setup complete'")
)
```

### Starting from a Docker Image

```python
image = (
    Image.from_image("python:3.11-slim")
    .pip_install("pandas", "matplotlib")
    .workdir("/app")
    .expose(8080)
    .entrypoint("python app.py")
)
```

### Chained Methods

| Method | Description |
|--------|-------------|
| `Image.from_template(name)` | Based on an existing template |
| `Image.from_image(ref)` | Based on a Docker image |
| `.pip_install(*pkgs)` | Install pip packages |
| `.apt_install(*pkgs)` | Install system packages |
| `.copy_local(src, dst)` | Copy local files |
| `.env(**kv)` | Set environment variables |
| `.run_command(cmd)` | Execute a command during build |
| `.workdir(path)` | Set the working directory |
| `.expose(*ports)` | Expose ports |
| `.entrypoint(cmd)` | Set the entrypoint command |

### Generate a Dockerfile

```python
dockerfile = image.to_dockerfile()
print(dockerfile)
# FROM python-base
# RUN pip install --no-cache-dir flask sqlalchemy
# RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*
# ENV DATABASE_URL=postgresql://localhost/mydb
# RUN echo 'setup complete'
```

### Build as a Template

```python
template_info = await image.build(
    alias="my-flask-app",  # Template alias
    timeout=600,           # Build timeout in seconds
    cpu_count=2,           # Default CPU
    memory_mb=4096,        # Default memory
    start_cmd="python app.py",  # Start command
)

print(f"Template ID: {template_info.template_id}")
print(f"Build status: {template_info.build_status.value}")

# Create a sandbox using the built template
sandbox = await Sandbox.create(template=template_info.template_id)
```

### Combining with the @sandbox Decorator

```python
from easy_sandbox.declarative import sandbox
from easy_sandbox.api.image import Image

image = Image.from_template("python-base").pip_install("flask")

@sandbox(image=image)
def my_app():
    from flask import Flask
    return "Flask ready"
```

The `image` parameter takes priority over the `template` parameter.

---

## Docker Build Process

The internal process for Image builds:

1. **Generate Dockerfile**: `image.to_dockerfile()` converts the chained calls into a Dockerfile
2. **Create HTTP client**: Using configured authentication credentials
3. **Call TemplateManager.build()**: Uploads the Dockerfile to the platform
4. **Wait for build completion**: Polls build status until `ready` or `error`
5. **Return TemplateInfo**: Contains `template_id` and build status

### Build-Related Errors

| Error | Code | Scenario |
|-------|------|----------|
| `TemplateBuildError` | E7010 | Template build failed |
| `TemplateBuildTimeoutError` | E7011 | Build timed out |
| `DockerBuildError` | E7020 | Local Docker build failed |
| `ACRPushError` | E7021 | Push to ACR failed |
| `ACRLoginError` | E7022 | ACR login failed |

---

## Next Steps

- [Authoring Templates](authoring-templates.md) — Define templates via template.yaml
- [SDK Usage Guide](sdk-usage.md) — Complete SDK usage
- [API Reference](../reference/api-reference.md) — Image class API details

## Related: the ebx CLI

The command-line template lifecycle (`ebx deploy`, `ebx template deploy`) is documented in the [`cli` repository](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/deploy-and-build.md).
