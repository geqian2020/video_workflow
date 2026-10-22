"""Call our own Office/Speech commands without changing Windows execution policy."""

import os
import subprocess
from pathlib import Path


def run_powershell(name: str, variables: dict[str, str], timeout: int):
    script = (Path(__file__).parent / "scripts" / name).read_text(encoding="utf-8")
    environment = os.environ.copy()
    environment.update(variables)
    # All executable text is shipped code. Paths and narration are data passed
    # through child-only environment variables and files, never interpolated code.
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
