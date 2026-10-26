"""Install each built artifact in its own venv and check all installed MCP scripts.

Run from the repository root after `python -m build`:
    python scripts/check_distribution.py dist
Only dependency installation uses the network; transport checks are offline.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv


def run(arguments: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 300) -> None:
    print("Running:", " ".join(arguments), flush=True)
    subprocess.run(arguments, cwd=cwd, env=env, check=True, timeout=timeout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="Directory containing one wheel and one source archive")
    args = parser.parse_args()
    wheels = list(args.dist.resolve().glob("*.whl"))
    sources = list(args.dist.resolve().glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        parser.error("Expected exactly one wheel and one .tar.gz source distribution")
    transport_test = Path(__file__).resolve().parents[1] / "tests" / "test_mcp_transport.py"
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME"}}
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    for artifact in [wheels[0], sources[0]]:
        print(f"\nChecking {artifact.name}", flush=True)
        with tempfile.TemporaryDirectory(prefix="bio-mcp-distribution-") as directory:
            root = Path(directory)
            environment = root / "venv"
            venv.EnvBuilder(with_pip=True).create(environment)
            python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            run([str(python), "-I", "-m", "pip", "install", str(artifact)], cwd=root, env=env)
            run([str(python), "-I", "-m", "pip", "check"], cwd=root, env=env)
            # Assert that imports cannot fall back to the source checkout.
            run([str(python), "-I", "-c",
                 "import pathlib, sys, servers, common; "
                 "prefix = pathlib.Path(sys.prefix).resolve(); "
                 "assert all(pathlib.Path(m.__file__).resolve().is_relative_to(prefix) "
                 "for m in (servers, common))"], cwd=root, env=env)
            tests = root / "tests"
            tests.mkdir()
            shutil.copyfile(transport_test, tests / transport_test.name)
            run([str(python), "-I", "-m", "unittest", "discover", "-s", str(tests), "-v"],
                cwd=root, env=env, timeout=180)


if __name__ == "__main__":
    main()
