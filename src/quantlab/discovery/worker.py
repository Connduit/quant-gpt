"""Minimal subprocess entrypoint: apply local resource limits before ML imports."""

import json
import os
import sys
import traceback
from pathlib import Path


def main():
    request = Path(sys.argv[1])
    job = json.loads(request.read_text())
    output = Path(job["output"])
    try:
        import resource

        limits = job["resources"]
        resource.setrlimit(
            resource.RLIMIT_CPU, (limits["trial_cpu_seconds"], limits["trial_cpu_seconds"] + 1)
        )
        memory = limits["memory_mb"] * 1024**2
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        # Tiny address-space caps can make native imports fail with opaque SystemError.
        # Reject below the declared supported footprint before importing scientific libraries.
        if limits["memory_mb"] < 512:
            raise MemoryError("Memory budget is below the supported 512 MiB worker minimum")
        if hasattr(os, "sched_setaffinity"):
            os.sched_setaffinity(0, set(job["cpu_affinity"]))
        from quantlab.discovery.evaluation import evaluate_candidate

        evaluate_candidate(
            job["definition"], output, progress_handshake=job.get("progress_handshake", False)
        )
    except BaseException as exc:
        (output / "failure.json").write_text(
            json.dumps(
                {
                    "type": type(exc).__name__,
                    "reason": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
