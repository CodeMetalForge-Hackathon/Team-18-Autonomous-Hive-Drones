"""Local executable discovery; contains no credentials or machine-specific user paths."""
import os
from pathlib import Path
import shutil
import signal
import subprocess


def find_node():
    override = os.environ.get("ROVER_NODE")
    if override:
        return shutil.which(override) or str(Path(override).expanduser())
    for name in ("node", "nodejs", "node.exe"):
        found = shutil.which(name)
        if found:
            return found
    # Standard Windows installation visible through WSL, without a user-home path.
    candidate = Path("/mnt/c/Program Files/nodejs/node.exe")
    return str(candidate) if candidate.is_file() else "node"


def node_available(node):
    return bool(shutil.which(node)) or Path(node).is_file()


def terminate_tree(process):
    """Stop a launched process and its children; os.killpg does not exist on Windows."""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def node_script_path(path, node):
    path = str(path)
    if node.lower().endswith(".exe") and path.startswith("/mnt/") and len(path) > 7:
        return path[5].upper() + ":\\" + path[7:].replace("/", "\\")
    return path
