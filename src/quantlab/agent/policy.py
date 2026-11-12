"""Independent authorization: exact datasets and vetted pipeline choices only."""

from copy import deepcopy
from pathlib import Path

import yaml

from quantlab.agent.schema import Budgets, Plan
from quantlab.discovery.common import code_version, fingerprint
from quantlab.futures.features import FEATURE_GROUPS
from quantlab.futures.research import load_futures_research, run_futures_research
from quantlab.futures.storage import FuturesStore


class ResearchTools:
    def __init__(self, configuration):
        self.path = Path(configuration).resolve()
        self.config = yaml.safe_load(self.path.read_text())
        if set(self.config) - {
            "dataset_id",
            "research_template",
            "budgets",
            "study_wall_seconds",
            "llm",
            "objective",
        }:
            raise ValueError("Unknown research-agent policy field")
        self.budgets = Budgets(**self.config.get("budgets", {}))
        self.template_path = (self.path.parent / self.config["research_template"]).resolve()
        self.template = load_futures_research(self.template_path)
        if self.template.get("resources", {}).get("workers", 1) != 1:
            raise ValueError("Agent policy permits one experiment worker")
        self.wall = self.config.get("study_wall_seconds", 300)
        if type(self.wall) is not int or not 10 <= self.wall <= min(
            900, self.budgets.max_runtime_seconds
        ):
            raise ValueError("Bound study wall time within session budget")
        store = FuturesStore(self.template["data"]["store"])
        self.datasets = {}
        self.products = set()
        cutoff = str(self.template["data"]["holdout_start"])
        for identifier in self.template["data"]["snapshots"]:
            manifest = store.manifest(identifier)
            if (
                manifest["synthetic"]
                or not manifest["tradable"]
                or manifest["price_basis"] != "actual_contract_unadjusted"
            ):
                raise ValueError("Agent policy requires verified actual-contract real inputs")
            if manifest["end"][:10] >= cutoff[:10]:
                raise ValueError(
                    "Agent snapshot overlaps reserved holdout; reject before pipeline execution"
                )
            self.datasets[identifier] = {
                k: manifest[k]
                for k in (
                    "provider",
                    "source",
                    "start",
                    "end",
                    "row_count",
                    "contract",
                    "quality",
                    "synthetic",
                )
            }
            self.products.add(manifest["contract"]["product"])
        self.experiments_per_study = 1 + 5 * len(self.products)
        self.identity = fingerprint(
            {
                "policy": self.config,
                "template": self.template,
                "datasets": self.datasets,
                "code": code_version()["source_sha256"],
            }
        )

    def context(self, history):
        return {
            "dataset_id": self.config["dataset_id"],
            "datasets": self.datasets,
            "allowed_feature_sets": self.template["search"]["feature_sets"],
            "allowed_models": list(self.template["search"]["models"]),
            "allowed_targets": self.template["search"]["targets"],
            "horizons": self.template["search"]["horizons"],
            "timeframes": self.template["search"]["decision_minutes"],
            "features": FEATURE_GROUPS,
            "actual_prior_iterations": history,
            "holdout_access": "FORBIDDEN",
            "permissions": [
                "inspect approved metadata",
                "propose bounded plan",
                "run fixed research pipeline",
                "inspect recorded results",
            ],
            "forbidden": [
                "live orders",
                "paper promotion",
                "holdout evaluation",
                "arbitrary file reads",
                "shell/code execution",
            ],
            "limits": (
                "Statistical eligibility is computed independently; two OOS sessions are "
                "insufficient."
            ),
        }

    def validate(self, proposal):
        plan = Plan.model_validate(proposal)
        s = self.template["search"]
        if (
            plan.dataset_id != self.config["dataset_id"]
            or set(plan.hypothesis.instruments) != self.products
        ):
            raise ValueError("Plan requests an unauthorized dataset/instrument scope")
        if plan.feature_set not in s["feature_sets"] or plan.model not in s["models"]:
            raise ValueError("Plan requests unauthorized features/model")
        if (
            plan.target not in s["targets"]
            or plan.horizon_minutes not in s["horizons"]
            or plan.decision_minutes not in s["decision_minutes"]
        ):
            raise ValueError("Plan exceeds approved target/timeframe scope")
        classification = plan.target in ("direction", "breakout_continuation")
        if (plan.model == "ridge" and classification) or (
            plan.model == "logistic" and not classification
        ):
            raise ValueError("Model incompatible with target")
        return plan

    def executable(self, plan):
        doc = deepcopy(self.template)
        doc["study"]["max_trials"] = 1
        doc["study"]["max_wall_seconds"] = self.wall
        s = doc["search"]
        s["models"] = {plan.model: s["models"][plan.model]}
        s["feature_sets"] = {plan.feature_set: s["feature_sets"][plan.feature_set]}
        s["targets"] = [plan.target]
        s["horizons"] = [plan.horizon_minutes]
        s["decision_minutes"] = [plan.decision_minutes]
        return doc

    def run(self, plan, output, *, stop_event, history_roots):
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        doc = self.executable(plan)
        configuration = output / "research.yaml"
        configuration.write_text(yaml.safe_dump(doc, sort_keys=False))
        return run_futures_research(
            configuration,
            output / "research",
            stop_event=stop_event,
            history_roots=history_roots,
            holdout_vault_path=Path(self.template["data"]["store"]).parent / "holdout-vault.sqlite",
        )

    @staticmethod
    def generated_code_proposal(text, directory):
        if not isinstance(text, str) or len(text.encode()) > 100000:
            raise ValueError("Bound code proposal text")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        # Store as text, never import/execute/apply or write production modules.
        path = directory / (fingerprint(text) + ".proposal.txt")
        path.write_text(text)
        return {
            "proposal": path.name,
            "executed": False,
            "review_required": True,
            "reason": (
                "Generated-code execution disabled until an independently verified OS sandbox "
                "exists"
            ),
        }
