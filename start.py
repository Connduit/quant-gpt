"""Start the local dashboard with the project's .env: python start.py."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000, help="Local port (default: 8000)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    root = Path(__file__).resolve().parent
    uv = shutil.which("uv")
    if not uv:
        print("Install uv first, then run python build.py.", file=sys.stderr)
        return 1
    if not (root / ".env").is_file():
        print("Copy .env.example to .env and fill in your settings first.", file=sys.stderr)
        return 1
    if not (root / "dashboard/dist/index.html").is_file():
        print("Build the dashboard first: python build.py", file=sys.stderr)
        return 1
    print(f"Starting dashboard at http://127.0.0.1:{args.port}", flush=True)
    try:
        subprocess.run(
            [
                uv, "run", "--env-file", str(root / ".env"), "--frozen", "--all-extras",
                "quantlab", "dashboard", "--host", "127.0.0.1", "--port", str(args.port),
            ],
            cwd=root,
            check=True,
        )
    except KeyboardInterrupt:
        return 130
    except subprocess.CalledProcessError as error:
        return error.returncode
    except OSError as error:
        print(f"Could not start the dashboard: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
