"""Install locked dependencies and build the local dashboard: python build.py."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    root = Path(__file__).resolve().parent
    commands = [
        ("uv", ["sync", "--frozen", "--all-extras"]),
        ("npm", ["--prefix", "dashboard", "ci"]),
        ("npm", ["--prefix", "dashboard", "run", "build"]),
    ]
    executables = {name: shutil.which(name) for name, _ in commands}
    missing = [name for name, path in executables.items() if not path]
    if missing:
        print("Install these tools first: " + ", ".join(missing), file=sys.stderr)
        return 1
    for name, arguments in commands:
        print("Running: " + " ".join([name, *arguments]), flush=True)
        try:
            subprocess.run([executables[name], *arguments], cwd=root, check=True)
        except subprocess.CalledProcessError as error:
            return error.returncode
        except OSError as error:
            print(f"Could not run {name}: {error}", file=sys.stderr)
            return 1
    print("Build complete. Start with:")
    print("python start.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
