"""CLI supervisor strips broker credentials before starting the research worker."""

import json
import os
import subprocess
import sys

from quantlab.agent.memory import Memory
from quantlab.agent.policy import ResearchTools
from quantlab.backtesting.report import dumps

ALLOWED_ENV = {
    "PATH",
    "LANG",
    "TZ",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "QUANTLAB_LLM_API_KEY",
}


def worker_environment(environment):
    return {k: v for k, v in environment.items() if k in ALLOWED_ENV} | {
        "CUDA_VISIBLE_DEVICES": "",
        "POLARS_MAX_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }


def execute(args):
    root = args.root.resolve()
    memory = Memory(root / "memory.sqlite")
    if args.agent_command in ("pause", "resume", "cancel", "emergency-stop"):
        memory.control(args.session, args.agent_command.replace("-", "_"), args.reason)
        print(
            dumps(
                {
                    "session": args.session,
                    "control_recorded": True,
                    "worker_restart_required": args.agent_command == "resume",
                }
            )
        )
        return 0
    if args.agent_command == "list":
        print(dumps(memory.sessions()))
        return 0
    if args.agent_command == "report":
        directory = root / "sessions" / args.session / "report.json"
        print(
            directory.read_text()
            if directory.exists()
            else dumps(
                {
                    "session": memory.session(args.session),
                    "iterations": memory.records(args.session),
                }
            )
        )
        return 0
    if args.agent_command == "propose-code":
        result = ResearchTools.generated_code_proposal(args.text.read_text(), root / "quarantine")
        print(dumps(result))
        return 0
    tools = ResearchTools(args.agent_config)
    identity = args.session or memory.create(
        args.objective or tools.config["objective"], tools.identity
    )
    argv = [
        sys.executable,
        "-m",
        "quantlab.agent.worker",
        "--configuration",
        str(tools.path),
        "--root",
        str(root),
        "--session",
        identity,
    ]
    if args.scripted_engineering:
        argv.append("--scripted-engineering")
    directory = root / "sessions" / identity
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "supervisor.log").open("a") as log:
        process = subprocess.Popen(
            argv, env=worker_environment(os.environ), stdout=log, stderr=subprocess.STDOUT
        )
        try:
            code = process.wait(timeout=tools.budgets.max_runtime_seconds + 45)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            memory.control(identity, "cancel", "supervisor timeout/interruption")
            try:
                code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                code = 1
    report = directory / "report.json"
    if not report.exists() or code:
        print(
            dumps(
                {"session": identity, "status": "FAILED", "log": str(directory / "supervisor.log")}
            )
        )
        return 1
    result = json.loads(report.read_text())
    print(
        dumps(
            {
                "session": identity,
                "status": result["session"]["status"],
                "report": str(report),
                "provider": result["provider"],
                "live_enabled": False,
            }
        )
    )
    return 0
