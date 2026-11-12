"""Pure v1 admission/defaulting; expressions are evaluated only by native Devs."""

from __future__ import annotations

import inspect
import json
import math
import re
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

DEFAULT_CONTRACT = json.loads(Path(__file__).with_name("contract.json").read_text())
Validator = Callable[[Any], Any]
MAX_YAML_BYTES = 1024 * 1024


def _fail(path: str, message: str) -> None:
    raise ValueError(f"Template v1 {path}: {message}")


def _expression(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("${") and value.endswith("}")


def _finite(value: Any, path: str = "/") -> None:
    if value is not None and not isinstance(value, (str, bool, int, float, list, dict)):
        _fail(path, "expected an interoperable JSON value")
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and abs(value) > 9007199254740991
    ) or (
        isinstance(value, float)
        and (
            not math.isfinite(value)
            or (value.is_integer() and abs(value) > 9007199254740991)
        )
    ):
        _fail(path, "expected a finite interoperable JSON number")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _finite(item, f"{path}/{index}")
    elif isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                _fail(path, "expected string JSON object keys")
            _finite(item, f"{'' if path == '/' else path}/{key}")


def parse_yaml_v1(source: str | bytes) -> Any:
    """Read bounded JSON-compatible YAML1.2 Core; no files, env or expression evaluation."""
    if not isinstance(source, (str, bytes)):
        raise TypeError("Template v1 /: expected YAML UTF-8 text or bytes")
    try:
        data = source.encode("utf-8", "strict") if isinstance(source, str) else source
        text = data.decode("utf-8", "strict")
    except UnicodeError:
        raise ValueError("Template v1 /: YAML must contain valid UTF-8") from None
    if len(data) > MAX_YAML_BYTES:
        _fail("/", "YAML exceeds 1 MiB")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
        _fail("/", "YAML contains unsupported control characters")

    # Library Core rules own scalar resolution; SafeLoader's YAML1.1 rules are
    # never changed globally. The subclass enforces only this source policy.
    from yaml.nodes import ScalarNode
    from yaml.tokens import AliasToken, DirectiveToken
    from yamlcore import CoreLoader

    class SourceLoader(CoreLoader):
        def get_token(self):
            token = super().get_token()
            if isinstance(token, AliasToken):
                raise TypeError("aliases are unsupported")
            if isinstance(token, DirectiveToken) and (
                token.name not in {"YAML", "TAG"}
                or (token.name == "YAML" and token.value != (1, 2))
            ):
                raise ValueError("only YAML1.2 directives are supported")
            return token

        def construct_object(self, node, deep=False):
            if (
                isinstance(node, ScalarNode)
                and node.tag
                in {
                    "tag:yaml.org,2002:bool",
                    "tag:yaml.org,2002:int",
                    "tag:yaml.org,2002:float",
                    "tag:yaml.org,2002:null",
                }
                and self.resolve(ScalarNode, node.value, (True, False)) != node.tag
            ):
                raise ValueError("explicit scalar tags cannot change the Core kind")
            return super().construct_object(node, deep=deep)

    loader = None
    try:
        loader = SourceLoader(text)
        value = loader.get_single_data()
        _finite(value)
        # Also reject invalid Unicode produced by escaped lone surrogate values.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8", "strict")
        return value
    except Exception:  # noqa: BLE001 - Parser errors contain source lines/values.
        raise ValueError(
            "Template v1 /: invalid JSON-compatible YAML1.2 Core: use one document "
            "with string keys; duplicate keys, aliases, unsupported tags and unsafe "
            "values are not allowed"
        ) from None
    finally:
        if loader is not None:
            loader.dispose()


def _checked(value: Any, validate: Validator) -> None:
    if not callable(validate):
        raise TypeError(
            "Pass an actual schema validator for the selected validation stage"
        )
    try:
        result = validate(value)
        if inspect.isawaitable(result):
            if hasattr(result, "close"):
                result.close()
            _fail("/", "use a synchronous schema validator")
        if result is False:
            _fail("/", "schema validation failed")
    except Exception as error:
        if isinstance(error, ValueError) and str(error).startswith("Template v1 "):
            raise error from None
        path = "/" + "/".join(str(key) for key in getattr(error, "path", []))
        raise ValueError(f"Template v1 {path}: schema validation failed") from None


def _fill(target: dict[str, Any], values: dict[str, Any]) -> None:
    for key, value in values.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(target[key], dict):
            _fill(target[key], value)


def _local_recipe(recipe: dict[str, Any], path: str) -> None:
    _fill(recipe, {"dockerfile": "Dockerfile", "context": "."})
    if (
        recipe["dockerfile"].startswith("/")
        or "\\" in recipe["dockerfile"]
        or "\0" in recipe["dockerfile"]
        or any(part in ("", ".", "..") for part in recipe["dockerfile"].split("/"))
    ):
        _fail(path + "/dockerfile", "expected a contained relative file path")


def _field_at(value: Any, path: str) -> tuple[bool, Any]:
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return False, None
        value = value[key]
    return True, value


def _numeric_order(parent: dict[str, Any], lower: str, upper: str, path: str) -> None:
    if (
        isinstance(parent[lower], (int, float))
        and isinstance(parent[upper], (int, float))
        and parent[lower] > parent[upper]
    ):
        _fail(path + "/" + lower, f"must be at most {upper}")


def schema_for_stage(schema: dict[str, Any], stage: str = "intent") -> dict[str, Any]:
    """Clone the intent schema for post-native-parser validation without evaluation."""
    if stage not in ("intent", "resolved"):
        raise ValueError("Unknown template validation stage")
    result = deepcopy(schema)
    if stage == "resolved":

        def strip(value: Any) -> Any:
            if isinstance(value, list):
                return [strip(item) for item in value]
            if not isinstance(value, dict):
                return value
            branches = value.get("oneOf")
            if (
                isinstance(branches, list)
                and branches
                and branches[-1].get("$ref") == "#/$defs/expression"
            ):
                alternatives = [strip(item) for item in branches[:-1]]
                return (
                    alternatives[0]
                    if len(alternatives) == 1
                    else {**value, "oneOf": alternatives}
                )
            return {key: strip(item) for key, item in value.items()}

        result = strip(result)
        result["$defs"]["secret"] = {"type": "string", "minLength": 1}
        result["properties"]["sandbox"]["required"] = ["provider", "template"]

    return result


def normalize_template_v1(
    manifest: dict[str, Any],
    validate: Validator,
    *,
    stage: str = "intent",
    contract: dict[str, Any] = DEFAULT_CONTRACT,
    provider: str | None = None,
    validate_provider: Callable[[str, Any, str], Any] | None = None,
) -> dict[str, Any]:
    """Validate a v1 document, fill its sole defaults and check cross-field invariants."""
    if stage not in ("intent", "resolved"):
        raise ValueError("Unknown template validation stage")
    _finite(manifest)
    result = deepcopy(manifest)
    if isinstance(result, dict) and isinstance(result.get("sandbox"), dict):
        declared = result["sandbox"].get("provider")
        if provider and declared and provider != declared:
            _fail("/sandbox/provider", "conflicts with the selected Provider context")
        if not declared and provider:
            result["sandbox"]["provider"] = provider
        if (
            not result["sandbox"].get("provider")
            and isinstance(result.get("application"), dict)
            and result["application"].get("type") == "agents-api"
        ):
            result["sandbox"]["provider"] = "alicloud-express"
    _checked(result, validate)
    sb, app = result.get("sandbox"), result.get("application")
    if sb:
        if "source" in sb["template"]:
            _local_recipe(sb["template"]["source"], "/sandbox/template/source")
            for name, recipe in sb["template"]["source"].get("profiles", {}).items():
                _local_recipe(recipe, "/sandbox/template/source/profiles/" + name)
        if sb["template"].get("reference") and sb["template"].get("props"):
            _fail(
                "/sandbox/template/props",
                "preparation properties cannot modify an existing template reference",
            )
        if not sb["template"].get("reference"):
            sb["template"].setdefault("props", {})
            if sb.get("provider") in contract["providerInputs"]:
                _fill(
                    sb["template"]["props"],
                    {
                        **contract["templateDefaults"],
                        **({"memory": 4096} if app else {}),
                    },
                )
        sb.setdefault("instance", {})
        _fill(
            sb["instance"],
            contract["managedInstanceDefaults"]
            if app
            else contract["instanceDefaults"],
        )
        sb.setdefault("services", {})
        for service in sb["services"].values():
            service.setdefault("operations", [])
        if (
            sb["instance"].get("lifecycle", {}).get("autoResume") is True
            and sb["instance"]["lifecycle"]["onTimeout"] != "pause"
        ):
            _fail("/sandbox/instance/lifecycle/autoResume", "requires onTimeout=pause")
        gpu = sb["instance"].get("gpu")
        if (
            sb.get("provider") == "opensandbox"
            and gpu
            and not re.fullmatch(r"[0-9]+", gpu)
            and not _expression(gpu)
        ):
            _fail(
                "/sandbox/instance/gpu",
                "this adapter accepts a numeric GPU count string",
            )
        resources = sb["template"].get("props")
        if (
            sb.get("provider") in contract["providerInputs"]
            and resources
            and isinstance(resources.get("memory"), (int, float))
        ):
            memory, cpu = resources["memory"], resources.get("cpu")
            if memory < 128 or memory % 64:
                _fail(
                    "/sandbox/template/props/memory",
                    "preparation memory is at least 128 MB and a multiple of 64",
                )
            if (
                sb.get("provider") == "alicloud-express"
                and isinstance(cpu, (int, float))
                and (memory < cpu * 1024 or memory > cpu * 4096)
            ):
                _fail(
                    "/sandbox/template/props/memory",
                    "Express preparation uses 1024..4096 MB per vCPU",
                )
        if (
            isinstance(sb["instance"]["timeout"], (int, float))
            and sb["instance"]["timeout"] > 86400
        ):
            _fail(
                "/sandbox/instance/timeout",
                "exceeds the high-level API limit of 86400 seconds",
            )
    if "deployment" in result:
        _fill(result["deployment"], {"name": result["name"], "access": "default"})
    if app:
        if sb["provider"] != "alicloud-express":
            _fail(
                "/sandbox/provider",
                "the current Managed consumer supports alicloud-express only",
            )
        app_defaults = deepcopy(contract["managedDefaults"])
        for auth in ("clientAuth", "internalAuth"):
            if auth in app["bindings"]:
                del app_defaults["bindings"][auth]
        _fill(app, app_defaults)
        if "source" in app["server"]:
            _local_recipe(app["server"]["source"], "/application/server/source")
        for key in ("start", "ready"):
            if key in sb and sb[key] != contract["managedSandbox"][key]:
                _fail("/sandbox/" + key, "conflicts with the Managed bridge runtime")
            sb[key] = contract["managedSandbox"][key]
        if sb["services"] and sb["services"] != contract["managedSandbox"]["services"]:
            _fail(
                "/sandbox/services",
                "the Managed bridge service is fixed by this application type",
            )
        sb["services"] = deepcopy(contract["managedSandbox"]["services"])
        selected = list(app["roles"].values())
        if len(set(selected)) != 3:
            _fail(
                "/application/roles",
                "each Managed role needs a distinct declared resource",
            )
        resource_names = set(result["deployment"]["resources"])
        for role, rid in app["roles"].items():
            if rid not in resource_names:
                _fail("/application/roles/" + role, "resource reference was not found")
            resource = result["deployment"]["resources"][rid]
            if not re.fullmatch(r"fc3@[0-9]+\.[0-9]+\.[0-9]+", resource["component"]):
                _fail(
                    "/deployment/resources/" + rid + "/component",
                    "the current Managed consumer requires a pinned fc3 component",
                )
            if (
                isinstance(resource["props"], dict)
                and resource["props"].get("runtime") is not None
                and resource["props"]["runtime"] != "custom-container"
                and not _expression(resource["props"]["runtime"])
            ):
                _fail(
                    "/deployment/resources/" + rid + "/props/runtime",
                    "the Managed bridge requires custom-container",
                )
            if isinstance(resource["props"], dict):
                for path in contract["protectedManagedProps"]:
                    if _field_at(resource["props"], path)[0]:
                        _fail(
                            "/deployment/resources/"
                            + rid
                            + "/props/"
                            + path.replace(".", "/"),
                            "this value is generated by the Managed coordinator",
                        )
        components = [
            result["deployment"]["resources"][rid]["component"] for rid in selected
        ]
        if len(set(components)) != 1:
            _fail(
                "/application/roles",
                "current Managed roles share one locked fc3 component version",
            )
        if (
            isinstance(app["sessions"]["idleTimeoutSeconds"], (int, float))
            and isinstance(sb["instance"]["timeout"], (int, float))
            and app["sessions"]["idleTimeoutSeconds"] > sb["instance"]["timeout"]
        ):
            _fail(
                "/application/sessions/idleTimeoutSeconds",
                "must be at most sandbox.instance.timeout",
            )
        _numeric_order(
            app["limits"], "maxToolSeconds", "maxRunSeconds", "/application/limits"
        )
        if (
            isinstance(app["limits"]["maxRunSeconds"], (int, float))
            and isinstance(sb["instance"]["timeout"], (int, float))
            and app["limits"]["maxRunSeconds"] >= sb["instance"]["timeout"]
        ):
            _fail(
                "/application/limits/maxRunSeconds",
                "must be less than sandbox.instance.timeout",
            )
        _numeric_order(
            app["storage"],
            "maxArtifactBytes",
            "maxTurnArtifactBytes",
            "/application/storage",
        )
        _numeric_order(
            app["storage"],
            "maxFileBytes",
            "maxRetainedBytesPerOwner",
            "/application/storage",
        )
        _numeric_order(
            app["storage"],
            "maxTurnArtifactBytes",
            "maxRetainedBytesPerOwner",
            "/application/storage",
        )
        if stage == "resolved":
            regions = [
                result["deployment"]["resources"][rid]["props"].get("region")
                for rid in selected
            ]
            if (
                any(
                    not isinstance(region, str)
                    or not re.fullmatch(r"cn-[a-z0-9-]+", region)
                    for region in regions
                )
                or len(set(regions)) != 1
            ):
                _fail(
                    "/application/roles",
                    "resolved Managed roles need the same supported literal region",
                )
            role_arns = [
                result["deployment"]["resources"][rid]["props"]["role"]
                for rid in selected
                if "role" in result["deployment"]["resources"][rid]["props"]
            ]
            if role_arns and (
                any(not isinstance(value, str) or not value for value in role_arns)
                or len(set(role_arns)) != 1
            ):
                _fail(
                    "/application/roles",
                    "the current Managed consumer uses one function RAM role",
                )
            if (
                role_arns
                and app["bindings"]["internalAuth"].get("roleArn")
                and role_arns[0] != app["bindings"]["internalAuth"]["roleArn"]
            ):
                _fail(
                    "/application/bindings/internalAuth/roleArn",
                    "conflicts with the declared native function role",
                )
            if app["bindings"]["sandboxAccess"]["region"] != regions[0]:
                _fail(
                    "/application/bindings/sandboxAccess/region",
                    "must match the resolved Managed FC region",
                )
    _checked(result, validate)
    if sb:
        if (
            stage == "resolved"
            and sb.get("provider") not in contract["providerInputs"]
            and not callable(validate_provider)
        ):
            _fail(
                "/sandbox/provider",
                "the selected plugin must supply real preparation/create validators",
            )
        if stage == "resolved" and validate_provider and sb.get("provider"):

            def invoke(stage: str, value: Any, path: str) -> None:
                try:
                    accepted = validate_provider(stage, deepcopy(value), sb["provider"])
                    if inspect.isawaitable(accepted):
                        if hasattr(accepted, "close"):
                            accepted.close()
                        _fail(path, "selected Provider validation failed")
                    if accepted is False:
                        _fail(path, "selected Provider validation failed")
                except Exception:  # noqa: BLE001 - Sanitize errors from external validators.
                    raise ValueError(
                        f"Template v1 {path}: selected Provider validation failed"
                    ) from None

            if not sb["template"].get("reference"):
                invoke("template.prepare", sb["template"], "/sandbox/template")
            invoke("sandbox.create", sb["instance"], "/sandbox/instance")
    return result


def compile_template_v1(
    manifest: dict[str, Any],
    validate: Validator,
    *,
    stage: str = "resolved",
    contract: dict[str, Any] = DEFAULT_CONTRACT,
    provider: str | None = None,
    validate_provider: Callable[[str, Any, str], Any] | None = None,
) -> dict[str, Any]:
    """Compile only resolved v1 input to private fields; never emit old spec versions."""
    if stage != "resolved":
        raise ValueError("Compile requires native-parser-resolved input")
    intent = normalize_template_v1(
        manifest,
        validate,
        stage=stage,
        contract=contract,
        provider=provider,
        validate_provider=validate_provider,
    )
    result: dict[str, Any] = {
        "name": intent["name"],
        "kind": "application"
        if intent.get("application")
        else "serving"
        if intent.get("deployment")
        else "sandbox",
    }
    if "deployment" in intent:
        result["deployment"] = deepcopy(intent["deployment"])
    if "sandbox" in intent:
        sb = intent["sandbox"]
        result.update(
            sandbox=deepcopy(sb),
            provider=sb["provider"],
            provides=deepcopy(sb["services"]),
            env=deepcopy(sb["instance"]["envs"]),
            ports=sorted(
                set(sb.get("ports", []))
                | {service["port"] for service in sb["services"].values()}
            ),
            resources=deepcopy(sb["template"].get("props", {})),
            start_cmd=sb.get("start"),
            ready_cmd=sb.get("ready"),
        )
        if sb["template"].get("aliases") is not None:
            result["aliases"] = deepcopy(sb["template"]["aliases"])
        if sb["template"].get("source", {}).get("profiles") is not None:
            result["build_profiles"] = deepcopy(sb["template"]["source"]["profiles"])
        if sb["template"].get("image"):
            result["image"] = sb["template"]["image"]
        if sb["template"].get("reference"):
            result["template_id"] = sb["template"]["reference"]
    if "application" in intent:
        app, dep = intent["application"], intent["deployment"]
        profile = deepcopy(contract["managedProfile"])
        gateway = dep["resources"][app["roles"]["gateway"]]
        binding_values = {"state": deepcopy(app["state"]), **deepcopy(app["bindings"])}
        binding_values["sandboxAccess"]["provider"] = intent["sandbox"]["provider"]
        native_role = next(
            (
                dep["resources"][rid]["props"]["role"]
                for rid in app["roles"].values()
                if "role" in dep["resources"][rid]["props"]
            ),
            None,
        )
        if native_role is not None:
            binding_values["internalAuth"]["roleArn"] = native_role
        compiled = deepcopy(profile["defaults"])
        _fill(
            compiled,
            {
                "sessions": app["sessions"],
                "limits": app["limits"],
                "storage": app["storage"],
            },
        )
        compiled["sessions"] = {
            **compiled["sessions"],
            **deepcopy(app["sessions"]),
            "maxLifetimeSeconds": intent["sandbox"]["instance"]["timeout"],
        }
        compiled["limits"] = deepcopy(app["limits"])
        compiled["storage"] = {**compiled["storage"], **deepcopy(app["storage"])}
        compiled["sandbox"]["provider"] = intent["sandbox"]["provider"]
        compiled["state"] = {**compiled["state"], "bindingRef": "state"}
        compiled["bindings"] = {
            name: {"reference": name, **deepcopy(options)}
            for name, options in profile["bindings"].items()
        }
        compiled["deployment"] = {
            **compiled["deployment"],
            "profile": "fc-managed-agents",
            "accessRef": dep["access"],
            "region": gateway["props"]["region"],
            "component": gateway["component"],
            "ingressBindingRef": "ingress",
            **(
                {"serverBuildRecipe": deepcopy(app["server"]["source"])}
                if "source" in app["server"]
                else {"serverImage": app["server"]["image"]}
            ),
        }
        if app.get("hooks"):
            compiled["hooks"] = deepcopy(app["hooks"])
        result["application"] = compiled
        result["bindingValues"] = binding_values
        result["roleResources"] = deepcopy(app["roles"])
        result["roleProps"] = {
            role: deepcopy(dep["resources"][rid]["props"])
            for role, rid in app["roles"].items()
        }
    return result


def pointer_value(document: Any, pointer: str) -> Any:
    """Decode a non-root JSON Pointer without accepting stale/implicit paths."""
    if (
        not isinstance(pointer, str)
        or not pointer.startswith("/")
        or re.search(r"~(?![01])", pointer)
    ):
        _fail("/questions/target", "expected a non-root JSON Pointer")
    value = document
    for encoded in pointer[1:].split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", key) or int(key) >= len(value):
                _fail("/questions/target", "target was not found")
            value = value[int(key)]
        else:
            if not isinstance(value, dict) or key not in value:
                _fail("/questions/target", "target was not found")
            value = value[key]
    return deepcopy(value)


def normalize_registry_v1(
    metadata: dict[str, Any],
    template: dict[str, Any],
    validate_registry: Validator,
    validate_template: Validator,
    *,
    contract: dict[str, Any] = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    """Validate optional metadata; runtime normalization never reads it."""
    _finite(metadata)
    _checked(metadata, validate_registry)
    result = deepcopy(metadata)
    intent = normalize_template_v1(template, validate_template, contract=contract)
    _fill(result, {"entry": "template.yaml", "questions": []})
    targets: set[str] = set()
    for index, question in enumerate(result["questions"]):
        if question["target"] in targets:
            _fail(f"/questions/{index}/target", "duplicate question target")
        targets.add(question["target"])
        value = pointer_value(intent, question["target"])
        if question.get("sensitive"):
            env = question["environmentVariable"]
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env) or value not in (
                "${env('" + env + "')}",
                '${env("' + env + '")}',
            ):
                _fail(
                    f"/questions/{index}/target",
                    "a sensitive question must target its declared native env expression",
                )
    return result
