"""App 2 – Document Conflict Resolver API."""
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv(Path(__file__).parent.parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import get_analysis, read_usage_log
from pipeline.config import DATA_DIR

_analysis: dict | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _analysis
    print("Loading analysis...")
    _analysis = get_analysis()
    print(f"Loaded: {len(_analysis.get('conflicts', []))} conflicts")
    yield


app = FastAPI(title="Conflict Resolver", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/analysis")
def get_full_analysis():
    return _analysis


@app.get("/api/conflicts")
def list_conflicts():
    return {
        "summary": _analysis.get("summary"),
        "count": len(_analysis.get("conflicts", [])),
        "conflicts": _analysis.get("conflicts", []),
        "documents": _analysis.get("documents", {}),
        "meta": _analysis.get("_meta", {}),
    }


@app.get("/api/usage")
def get_usage():
    """Token usage and cost summary across all LLM calls."""
    return read_usage_log()


class ResolutionPayload(BaseModel):
    conflict_id: str
    decision: str
    resolved_by: str = "Expert"


RESOLUTIONS_PATH = Path(os.environ.get("RESOLUTIONS_PATH", DATA_DIR / "resolutions.json"))


def load_resolutions() -> dict:
    if RESOLUTIONS_PATH.exists():
        return json.loads(RESOLUTIONS_PATH.read_text())
    return {}


def save_resolutions(data: dict):
    RESOLUTIONS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))


@app.post("/api/resolve")
def resolve_conflict(payload: ResolutionPayload):
    resolutions = load_resolutions()
    resolutions[payload.conflict_id] = {
        "decision": payload.decision,
        "resolved_by": payload.resolved_by,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }
    save_resolutions(resolutions)
    return {"status": "saved", "conflict_id": payload.conflict_id}


@app.get("/api/resolutions")
def get_resolutions():
    return load_resolutions()


@app.post("/api/reanalyze")
def reanalyze():
    global _analysis
    _analysis = get_analysis(force=True)
    return {"status": "done", "conflicts": len(_analysis.get("conflicts", []))}


@app.get("/api/health")
def health():
    return {"status": "ok"}
