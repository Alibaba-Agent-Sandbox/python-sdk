"""Agent Sandbox runtime metadata for the ported protocol client."""
import platform
from agent_sandbox._version import __version__

package_version = __version__
default_headers = {"lang": "python", "lang_version": platform.python_version(),
 "package_version": __version__, "publisher": "agent-sandbox",
 "sdk_runtime": "python", "system": platform.system()}
