from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any


PACKAGE_NAME = "cad-translate"
PACKAGE_VERSION = "1.0.1"
ENTRY_POINT = "cad-translate"


def harness_root() -> Path:
    return Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    return harness_root()


def dist_dir() -> Path:
    return harness_root() / "dist"


def package_info() -> dict[str, Any]:
    return {
        "success": True,
        "package_name": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
        "entry_point": ENTRY_POINT,
        "harness_root": str(harness_root()),
        "dist_dir": str(dist_dir()),
        "release_steps": [
            f"{ENTRY_POINT} release build",
            f"{ENTRY_POINT} release smoke",
        ],
    }


def build_distributions(output_dir: str | Path | None = None) -> dict[str, Any]:
    root = harness_root()
    target = Path(output_dir) if output_dir is not None else dist_dir()
    target.mkdir(parents=True, exist_ok=True)

    command = [sys.executable, "-m", "build", "--outdir", str(target), "--no-isolation"]
    completed = subprocess.run(
        command,
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Build command failed: {' '.join(command)}\n{completed.stderr.strip() or completed.stdout.strip()}"
        )

    artifacts = sorted(str(path) for path in target.glob("*") if path.is_file())
    return {
        "success": True,
        "package_name": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
        "dist_dir": str(target),
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "build_command": " ".join(command),
        "builder": "python -m build",
    }


def run_smoke_checks() -> dict[str, Any]:
    root = harness_root()
    argv_launcher = Path(sys.argv[0]).resolve()
    launcher = None
    if argv_launcher.exists() and ENTRY_POINT in argv_launcher.name:
        launcher = str(argv_launcher)
    if launcher is None:
        launcher = shutil.which(ENTRY_POINT)
    if launcher is None:
        userbase = sysconfig.get_config_var("userbase") or ""
        scripts_dir = Path(userbase) / f"Python{sys.version_info.major}{sys.version_info.minor}" / "Scripts"
        for candidate in (scripts_dir / f"{ENTRY_POINT}.exe", scripts_dir / f"{ENTRY_POINT}-script.py"):
            if candidate.exists():
                launcher = str(candidate)
                break
    env = os.environ.copy()

    if launcher:
        commands = [
            [launcher, "--help"],
            [launcher, "--json", "project", "new", "--name", "smoke-demo"],
        ]
        module_entry = launcher
    else:
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(root) if not existing_pythonpath else os.pathsep.join([str(root), existing_pythonpath])
        commands = [
            [sys.executable, "-m", "cli", "--help"],
            [sys.executable, "-m", "cli", "--json", "project", "new", "--name", "smoke-demo"],
        ]
        module_entry = f"{sys.executable} -m cli"

    results: list[dict[str, Any]] = []
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=str(repo_root()),
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        result = {
            "command": " ".join(command),
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
        results.append(result)
        if completed.returncode != 0:
            raise RuntimeError(
                f"Smoke check failed: {' '.join(command)}\n{completed.stderr.strip() or completed.stdout.strip()}"
            )

    return {
        "success": True,
        "package_name": PACKAGE_NAME,
        "version": PACKAGE_VERSION,
        "entry_point": ENTRY_POINT,
        "module_entry": module_entry,
        "dist_dir": str(dist_dir()),
        "installed_launcher_found": launcher is not None,
        "checks_passed": [result["command"] for result in results],
        "check_count": len(results),
    }
