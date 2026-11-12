"""Credential-restricted fixed research worker; generated code is never evaluated."""

import argparse
import resource
import signal
from pathlib import Path

from quantlab.agent.memory import Memory
from quantlab.agent.policy import ResearchTools
from quantlab.agent.runner import Agent, provider_from_policy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--scripted-engineering", action="store_true")
    args = parser.parse_args()
    tools = ResearchTools(args.configuration)
    resource.setrlimit(
        resource.RLIMIT_CPU,
        (tools.budgets.max_runtime_seconds, tools.budgets.max_runtime_seconds + 1),
    )
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024**3, 8 * 1024**3))
    memory = Memory(args.root / "memory.sqlite")

    def stop(signum, frame):
        memory.control(args.session, "cancel", "worker termination signal")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    workspace = tools.template_path.parent.parent
    agent = Agent(
        tools,
        memory,
        args.root,
        provider_from_policy(tools, scripted=args.scripted_engineering),
        history_roots=[
            workspace / "data/discovery",
            workspace / "data/statistical",
            workspace / "data/futures",
            args.root,
        ],
    )
    agent.run(args.session)


if __name__ == "__main__":
    main()
