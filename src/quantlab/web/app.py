"""Versioned read-mostly API; paper controls and research jobs require roles."""

import asyncio
import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from starlette.exceptions import HTTPException as StarletteHTTPException

from quantlab.agent.memory import Memory
from quantlab.paper.store import PaperStore
from quantlab.web.catalog import KINDS, Catalog
from quantlab.web.credentials import ProviderKeyStore
from quantlab.web.jobs import JobManager
from quantlab.web.workflows import (
    DownloadRequest,
    ProfitabilityRequest,
    ResearchRequest,
    selected_snapshots,
    snapshot_inventory,
)


class Artifact(BaseModel):
    id: str
    kind: str
    label: str
    mode: str
    status: str
    summary: dict[str, Any]
    updated_at: str


class ArtifactPage(BaseModel):
    items: list[Artifact]
    total: int
    offset: int
    limit: int


class Detail(BaseModel):
    record: Artifact
    data: dict[str, Any]
    series: list[dict[str, Any]]


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["resume", "pause", "stop", "kill"]
    strategy: str | None = Field(None, max_length=100)
    reason: str = Field(min_length=3, max_length=500)
    confirmed: Literal[True]


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    confirmed: Literal[True]


class AlpacaKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key_id: SecretStr = Field(min_length=8, max_length=512)
    secret_key: SecretStr = Field(min_length=8, max_length=512)
    confirmed: Literal[True]


class DatabentoKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=8, max_length=512)
    confirmed: Literal[True]


class RemoveKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: Literal[True]


class AgentStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scripted-agent-engineering", "approved-agent-research"]
    objective: str | None = Field(None, min_length=10, max_length=1200)
    confirmed: Literal[True]


class AgentControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "cancel", "emergency_stop"]
    reason: str = Field(min_length=3, max_length=500)
    confirmed: Literal[True]


class Health(BaseModel):
    status: str
    live_enabled: bool
    streaming_verified: bool
    eligible_strategies: int
    warnings: list[str]
    jobs: list[dict[str, Any]]
    paper_accounts: int
    catalog_errors: list[str]
    holdout_state: str


class SPAFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api/") and "." not in path:
                return await super().get_response("index.html", scope)
            raise


def create_app(
    catalog: Catalog,
    *,
    state_root,
    tokens=None,
    local_reads=True,
    approved_jobs=None,
    frontend=None,
    workflow_library=None,
):
    tokens = tokens or {}
    if any(
        role not in ("viewer", "operator", "researcher") or len(token) < 24
        for token, role in tokens.items()
    ):
        raise ValueError("Unique role tokens must contain at least 24 characters")
    key_store = ProviderKeyStore(Path(state_root) / "credentials")
    jobs = JobManager(
        Path(state_root) / "jobs", approved_jobs, provider_credentials=key_store.credentials
    )
    library = Path(workflow_library or (Path(state_root) / "library")).resolve()
    audit = Path(state_root) / "api-audit.jsonl"
    audit.parent.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()

    app = FastAPI(title="Quant Research Lab", version="1", lifespan=lifespan)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.state.jobs = jobs
    app.state.catalog = catalog

    def role(request: Request):
        auth = request.headers.get("authorization", "")
        supplied = auth[7:] if auth.startswith("Bearer ") else ""
        for token, assigned in tokens.items():
            if supplied and hmac.compare_digest(supplied.encode(), token.encode()):
                return assigned
        if auth:
            raise HTTPException(401, "Invalid access token")
        if (
            local_reads
            and request.client
            and request.client.host in ("127.0.0.1", "::1", "testclient")
        ):
            return "local_viewer"
        raise HTTPException(401, "Authentication required")

    access = Depends(role)

    def require(assigned, allowed):
        if assigned not in allowed:
            raise HTTPException(403, "Role does not authorize this operation")

    def credential_access(request, assigned):
        require(assigned, ("operator",))
        loopback = (
            request.client
            and request.client.host in ("127.0.0.1", "::1", "testclient")
            and request.url.hostname in ("localhost", "127.0.0.1", "::1", "testserver")
        )
        if request.url.scheme != "https" and not loopback:
            raise HTTPException(403, "Provider keys require HTTPS or a loopback connection")

    def log(action, assigned, detail):
        with audit.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "at": datetime.now(UTC).isoformat(),
                        "action": action,
                        "role": assigned,
                        "detail": detail,
                    }
                )
                + "\n"
            )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": str(exc.status_code), "message": exc.detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        message = "Invalid request schema"
        # Return schema explanations for the non-secret strategy form, never submitted
        # values/exception contexts. Credential and other routes retain generic errors.
        if request.url.path == "/api/v1/workflows/profitability":
            explanations = []
            for error in exc.errors()[:8]:
                location = error.get("loc", ())
                kind = error.get("type", "")
                field = str(location[-1]) if location else ""
                if kind == "value_error" and location == ("body",):
                    reason = str(error.get("ctx", {}).get("error", ""))
                    if reason.startswith("Phase 12C cannot"):
                        explanations.append(
                            "The evaluation includes the protected 2019 equity holdout. "
                            "Use a separately downloaded snapshot and training run ending by "
                            "2018-12-31 or starting on/after "
                            "2020-01-01. Changing only the backtest dates cannot make a "
                            "source run containing protected data eligible."
                        )
                    elif reason in (
                        "start must be on or before end (both dates are inclusive)",
                        "Only completed historical dates before today are supported",
                        "Profitability evaluation permits at most ten years",
                    ):
                        explanations.append(reason)
                    else:
                        explanations.append("Check the evaluation start and end dates.")
                elif field in ProfitabilityRequest.model_fields and kind != "extra_forbidden":
                    label = field.replace("_", " ")
                    if field == "source_job_id":
                        explanations.append("Select a saved ML report from the workflow job list.")
                    else:
                        explanations.append(f"{label}: {error.get('msg', 'Invalid field')}")
                else:
                    explanations.append("The evaluation request contains unsupported fields.")
            message = " ".join(dict.fromkeys(explanations)) or message
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation", "message": message}},
        )

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse(
            status_code=400, content={"error": {"code": "invalid_operation", "message": str(exc)}}
        )

    def detail(identity):
        try:
            return {
                "record": catalog.record(identity),
                "data": catalog.document(identity),
                "series": catalog.series(identity),
            }
        except (KeyError, FileNotFoundError) as exc:
            raise HTTPException(404, "Artifact not found or unavailable") from exc
        except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
            raise HTTPException(503, "Artifact cannot be read safely") from exc

    def health():
        records = catalog.index()
        warnings = [
            "External streaming is unverified; historical replay is not live paper evidence.",
            "No strategy is approved for live execution.",
            "Reserved holdouts must remain sealed.",
            "Stooq is still blocked in the attached older runtime configuration.",
        ]
        if catalog.errors:
            warnings.append(
                "Some cataloged artifacts are unavailable; no fixture substitution was made."
            )
        states = []
        for ledger in (
            catalog.workspace / "data/network-verification/holdout-vault.sqlite",
            catalog.workspace / "data/futures/holdout-vault.sqlite",
        ):
            if ledger.is_file():
                try:
                    with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as db:
                        states.extend(row[0] for row in db.execute("SELECT state FROM holdouts"))
                except sqlite3.Error:
                    states.append("UNREADABLE")
                    warnings.append(
                        "Holdout ledger cannot be verified; authorization remains unavailable."
                    )
        holdout_state = (
            "SEALED" if states and all(x == "SEALED" for x in states) else "UNKNOWN_OR_CHANGED"
        )
        eligible = 0
        for row in records:
            if row["kind"] == "paper":
                strategies = catalog.document(row["id"]).get("strategies", {})
                eligible += sum(
                    s.get("validation_status") == "VALIDATED" and s.get("deployment") != "RESEARCH"
                    for s in strategies.values()
                )
        return {
            "holdout_state": holdout_state,
            "status": "LIMITED",
            "live_enabled": False,
            "streaming_verified": False,
            "eligible_strategies": eligible,
            "warnings": warnings,
            "jobs": jobs.rows(),
            "paper_accounts": sum(r["kind"] == "paper" for r in records),
            "catalog_errors": list(catalog.errors),
        }

    @app.get("/api/v1/health", response_model=Health)
    def get_health(assigned=access):
        return health()

    @app.get("/api/v1/artifacts", response_model=ArtifactPage)
    def artifacts(
        kind: str | None = None,
        search: str = Query("", max_length=120),
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        sort: Literal["updated_at", "label", "status"] = "updated_at",
        assigned=access,
    ):
        if kind is not None and kind not in KINDS:
            raise HTTPException(422, "Unsupported artifact kind")
        rows = catalog.index(kind=kind, search=search, sort=sort)
        return {
            "items": rows[offset : offset + limit],
            "total": len(rows),
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/v1/artifacts/{identity}", response_model=Detail)
    def artifact(identity: str, assigned=access):
        return detail(identity)

    @app.get("/api/v1/compare")
    def compare(ids: str = Query(max_length=150), assigned=access):
        selected = ids.split(",")
        if not 2 <= len(selected) <= 4:
            raise HTTPException(422, "Compare two to four curated IDs")
        return {"items": [detail(identity)["record"] for identity in selected]}

    @app.get("/api/v1/overview")
    def overview(assigned=access):
        records = catalog.index()
        paper = next((r for r in records if r["kind"] == "paper"), None)
        return {"items": records[:8], "paper": detail(paper["id"]) if paper else None}

    @app.get("/api/v1/jobs")
    def list_jobs(assigned=access):
        return {
            "items": jobs.rows(),
            "approved": sorted(
                name
                for name, spec in jobs.approved.items()
                if spec["arguments"] != ["dashboard-workflow"]
            ),
        }

    @app.get("/api/v1/workflows/snapshots")
    def workflow_snapshots(
        start: date | None = None,
        end: date | None = None,
        research_mode: Literal["strict", "exploratory"] = "strict",
        assigned=access,
    ):
        return snapshot_inventory(library, start=start, end=end, research_mode=research_mode)

    @app.get("/api/v1/workflows/providers")
    def workflow_providers(assigned=access):
        return key_store.status()

    @app.get("/api/v1/settings/providers")
    def credential_status(assigned=access):
        return {**key_store.status(), "editable": assigned == "operator"}

    @app.put("/api/v1/settings/providers/alpaca")
    def save_alpaca_keys(body: AlpacaKeys, request: Request, assigned=access):
        credential_access(request, assigned)
        key_store.save(
            "alpaca",
            {
                "APCA_API_KEY_ID": body.key_id.get_secret_value(),
                "APCA_API_SECRET_KEY": body.secret_key.get_secret_value(),
            },
        )
        log("provider_keys_saved", assigned, {"provider": "alpaca"})
        return {"status": "SAVED", "provider": "alpaca"}

    @app.put("/api/v1/settings/providers/databento")
    def save_databento_key(body: DatabentoKeys, request: Request, assigned=access):
        credential_access(request, assigned)
        key_store.save("databento", {"DATABENTO_API_KEY": body.api_key.get_secret_value()})
        log("provider_keys_saved", assigned, {"provider": "databento"})
        return {"status": "SAVED", "provider": "databento"}

    @app.delete("/api/v1/settings/providers/{provider}")
    def remove_provider_keys(
        provider: Literal["alpaca", "databento"],
        body: RemoveKeys,
        request: Request,
        assigned=access,
    ):
        credential_access(request, assigned)
        key_store.remove(provider)
        log("provider_keys_removed", assigned, {"provider": provider})
        return {"status": "REMOVED", "provider": provider}

    @app.post("/api/v1/workflows/download", status_code=202)
    def workflow_download(body: DownloadRequest, assigned=access):
        require(assigned, ("researcher",))
        identity = jobs.submit_workflow(
            "download", body.model_dump(mode="json"), library, catalog.workspace
        )
        log(
            "historical_download",
            assigned,
            {"id": identity, "request": body.model_dump(mode="json")},
        )
        return {"id": identity, "status": "QUEUED"}

    @app.post("/api/v1/workflows/research", status_code=202)
    def workflow_research(body: ResearchRequest, assigned=access):
        require(assigned, ("researcher",))
        try:
            selected_snapshots(library, body)
        except FileNotFoundError as exc:
            raise HTTPException(422, "Selected snapshot is not available in the library") from exc
        identity = jobs.submit_workflow(
            body.workflow, body.model_dump(mode="json"), library, catalog.workspace
        )
        log(
            "equity_" + body.workflow,
            assigned,
            {"id": identity, "request": body.model_dump(mode="json")},
        )
        return {"id": identity, "status": "QUEUED"}

    @app.post("/api/v1/workflows/profitability", status_code=202)
    def workflow_profitability(body: ProfitabilityRequest, assigned=access):
        require(assigned, ("researcher",))
        identity = jobs.submit_workflow(
            "profitability", body.model_dump(mode="json"), library, catalog.workspace
        )
        log(
            "profitability_evaluation",
            assigned,
            {"id": identity, "request": body.model_dump(mode="json")},
        )
        return {"id": identity, "status": "QUEUED"}

    @app.get("/api/v1/workflows/jobs/{identity}/profitability.zip")
    def profitability_artifacts(identity: str, assigned=access):
        if not any(row["id"] == identity and row["status"] == "COMPLETED" for row in jobs.rows()):
            raise HTTPException(404, "Completed profitability job not found")
        path = (jobs.root / identity / "artifacts/profitability.zip").resolve()
        if not path.is_relative_to(jobs.root.resolve()) or not path.is_file():
            raise HTTPException(404, "Profitability artifacts not available")
        return FileResponse(
            path, media_type="application/zip", filename=f"profitability-{identity}.zip"
        )

    @app.get("/api/v1/workflows/jobs/{identity}")
    def workflow_result(identity: str, assigned=access):
        try:
            result = jobs.result(identity)
        except KeyError as exc:
            raise HTTPException(404, "Unknown job") from exc
        return {"result": catalog.redact(result)}

    @app.post("/api/v1/jobs", status_code=202)
    def submit_job(body: JobRequest, assigned=access):
        require(assigned, ("researcher",))
        identity = jobs.submit(body.name)
        log("job_submit", assigned, {"id": identity, "name": body.name})
        return {"id": identity, "status": "QUEUED"}

    @app.post("/api/v1/jobs/{identity}/cancel", status_code=202)
    def cancel_job(identity: str, body: JobRequest, assigned=access):
        require(assigned, ("researcher",))
        try:
            jobs.cancel(identity)
        except KeyError as exc:
            raise HTTPException(404, "Unknown job") from exc
        log("job_cancel", assigned, {"id": identity})
        return {"id": identity, "status": "CANCELLATION_REQUESTED"}

    @app.post("/api/v1/paper/{identity}/control", status_code=202)
    def paper_control(identity: str, body: Control, assigned=access):
        require(assigned, ("operator",))
        try:
            entry = catalog.entry(identity)
        except KeyError as exc:
            raise HTTPException(404, "Unknown paper account") from exc
        if entry["kind"] != "paper" or not entry.get("database"):
            raise HTTPException(400, "Not a controllable simulated account")
        database = entry["database"]
        if not database.is_file():
            raise HTTPException(404, "Account database unavailable")
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
            row = db.execute("SELECT payload FROM state WHERE id=1").fetchone()
            state = json.loads(row[0])
        if body.action == "resume":
            strategy = state["strategies"].get(body.strategy)
            if (
                not strategy
                or strategy["validation_status"] != "VALIDATED"
                or strategy["deployment"] == "RESEARCH"
            ):
                raise HTTPException(409, "Strategy lacks validated paper deployment approval")
        PaperStore.queue(database, body.model_dump(exclude={"confirmed"}))
        log(
            "paper_control",
            assigned,
            {"account": identity, **body.model_dump(exclude={"confirmed"})},
        )
        return {"queued": True, "applied": False, "execution": "SIMULATED"}

    @app.get("/api/v1/execution/readiness")
    def execution_readiness(assigned=access):
        from quantlab.execution.readiness import readiness

        return readiness(catalog.workspace)

    @app.get("/api/v1/execution/capabilities")
    def execution_capabilities(assigned=access):
        return {
            "modes": ["BACKTEST", "PAPER", "BROKER_SANDBOX"],
            "live_enabled": False,
            "live_controls": False,
            "broker_adapter": "Alpaca PAPER only",
            "futures_brokerage": "UNAVAILABLE",
            "order_entry_api": "UNAVAILABLE",
            "strategy_promotion_api": "UNAVAILABLE",
        }

    agent_root = catalog.workspace / "data/agent"

    @app.get("/api/v1/agent/sessions")
    def agent_sessions(assigned=access):
        path = agent_root / "memory.sqlite"
        return {
            "items": Memory(path).sessions() if path.is_file() else [],
            "execution": "research_only",
            "live_enabled": False,
        }

    @app.get("/api/v1/agent/sessions/{identity}")
    def agent_session(identity: str, assigned=access):
        if not (agent_root / "memory.sqlite").is_file():
            raise HTTPException(404, "No research sessions")
        memory = Memory(agent_root / "memory.sqlite")
        try:
            session = memory.session(identity)
        except KeyError as exc:
            raise HTTPException(404, "Unknown research session") from exc
        return catalog.redact(
            {
                "session": session,
                "iterations": memory.records(identity),
                "events": memory.events(identity),
                "live_enabled": False,
            }
        )

    @app.post("/api/v1/agent/sessions", status_code=202)
    def start_agent(body: AgentStart, assigned=access):
        require(assigned, ("researcher",))
        if body.name not in ("scripted-agent-engineering", "approved-agent-research"):
            raise HTTPException(400, "Unknown approved agent workflow")
        name = body.name
        if body.objective:
            base = jobs.approved.get(name)
            if base is None:
                raise HTTPException(400, "Agent workflow is not configured")
            name = "agent-objective-" + uuid.uuid4().hex
            jobs.approved[name] = {
                **base,
                "arguments": [*base["arguments"], "--objective=" + body.objective],
            }
        identity = jobs.submit(name)
        log("agent_start", assigned, {"job": identity, "workflow": body.name})
        return {"job": identity, "queued": True, "live_enabled": False}

    @app.post("/api/v1/agent/sessions/{identity}/control", status_code=202)
    def agent_control(identity: str, body: AgentControl, assigned=access):
        require(assigned, ("researcher",))
        if not (agent_root / "memory.sqlite").is_file():
            raise HTTPException(404, "Unknown research session")
        memory = Memory(agent_root / "memory.sqlite")
        try:
            memory.session(identity)
            memory.control(identity, body.action, body.reason)
        except KeyError as exc:
            raise HTTPException(404, "Unknown research session") from exc
        if body.action == "resume":
            base = jobs.approved.get("scripted-agent-engineering")
            if base is None:
                raise HTTPException(409, "No reviewed resume workflow configured")
            name = "resume-agent-" + identity
            jobs.approved[name] = {**base, "arguments": [*base["arguments"], "--session", identity]}
            jobs.submit(name)
        log("agent_control", assigned, {"session": identity, **body.model_dump()})
        return {"control_recorded": True, "applied": False, "live_enabled": False}

    @app.get("/api/v1/events")
    async def events(request: Request, assigned=access):
        async def generate():
            for _ in range(240):
                if await request.is_disconnected():
                    break
                yield (
                    "event: refresh\ndata: "
                    + json.dumps({"at": datetime.now(UTC).isoformat(), "mode": "monitoring_notice"})
                    + "\n\n"
                )
                await asyncio.sleep(15)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    if frontend:
        frontend = Path(frontend)
        if frontend.is_dir():
            app.mount("/", SPAFiles(directory=frontend, html=True), name="frontend")
    return app


def from_environment():
    workspace = Path(os.environ.get("QUANTLAB_WORKSPACE", Path.cwd())).resolve()
    catalog = Catalog(
        os.environ.get("QUANTLAB_CATALOG", workspace / "configs/dashboard.catalog.yaml"), workspace
    )
    tokens = {}
    for role in ("viewer", "operator", "researcher"):
        token = os.environ.get("QUANTLAB_" + role.upper() + "_TOKEN")
        if token:
            if token in tokens:
                raise ValueError("Role tokens must be distinct")
            tokens[token] = role
    bind = os.environ.get("QUANTLAB_BIND_HOST", "127.0.0.1")
    if bind not in ("127.0.0.1", "::1", "localhost") and not tokens:
        raise ValueError("Nonlocal hosting requires configured authentication")
    approved = {}
    configuration = workspace / "configs/futures-research.example.yaml"
    if configuration.is_file():
        approved["archival-futures-research"] = {
            "arguments": ["futures", "research", "--research-config", str(configuration)],
            "configuration_sha256": hashlib.sha256(configuration.read_bytes()).hexdigest(),
            "configuration": str(configuration),
            "workspace": str(workspace),
            "wall_seconds": 1200,
        }
    agent_configuration = workspace / "configs/agent.example.yaml"
    if agent_configuration.is_file():
        approved["scripted-agent-engineering"] = {
            "arguments": [
                "agent",
                "run",
                "--agent-config",
                str(agent_configuration),
                "--root",
                str(workspace / "data/agent"),
                "--scripted-engineering",
            ],
            "configuration": str(agent_configuration),
            "configuration_sha256": hashlib.sha256(agent_configuration.read_bytes()).hexdigest(),
            "workspace": str(workspace),
            "wall_seconds": 1000,
        }
    return create_app(
        catalog,
        state_root=workspace / "data/dashboard",
        tokens=tokens,
        local_reads=bind in ("127.0.0.1", "::1", "localhost"),
        approved_jobs=approved,
        workflow_library=os.environ.get("QUANTLAB_WORKFLOW_LIBRARY"),
        frontend=workspace / "dashboard/dist",
    )
