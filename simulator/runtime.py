"""Local executable discovery; contains no credentials or machine-specific user paths."""
import os
from pathlib import Path
import shutil


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


def node_script_path(path, node):
    path = str(path)
    if node.lower().endswith(".exe") and path.startswith("/mnt/") and len(path) > 7:
        return path[5].upper() + ":\\" + path[7:].replace("/", "\\")
    return path
