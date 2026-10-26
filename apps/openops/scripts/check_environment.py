"""Read-only dependency check. Does not display secrets or install software."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    local = Path(os.environ.get("LOCALAPPDATA", "."))
    result = {
        "python_available": True,
        "docker_command_available": shutil.which("docker") is not None,
        "java_command_available": shutil.which("java") is not None,
        "nightshift_cli_at_documented_path": (local / "Nightshift/cli/ns.cmd").exists(),
        "zetaris_rest_port_8888_open": port_open(8888),
        "zetaris_jdbc_port_10000_open": port_open(10000),
        "nightshift_port_8088_open": port_open(8088),
        "jaydebeapi_importable": importlib.util.find_spec("jaydebeapi") is not None,
        "notes": [
            "Open ports do not establish service identity or authenticated readiness.",
            "Java presence does not establish a compatible version.",
            "No credentials were inspected; no dependencies were installed.",
        ],
    }
    print(json.dumps(result, indent=2))
