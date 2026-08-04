from datetime import datetime, timezone

import networkx as nx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from starlette.middleware.base import BaseHTTPMiddleware
from database import Base, engine, AsyncSessionLocal, Business
from routers.admin import router as admin_router
from routers.assistant import router as assistant_router
from routers.audit import router as audit_router
from routers.compliance import router as compliance_router
from routers.gst import router as gst_router
from routers.hitl import router as hitl_router
from routers.knowledge import router as knowledge_router
from routers.obligations import router as obligations_router
from routers.payroll import router as payroll_router
from routers.demo import router as demo_router
from websocket.retrigger_ws import router as websocket_router, manager
from middleware.clerk_auth import clerk_auth_middleware
from services.knowledge.obligation_graph.graph_builder import ObligationGraphBuilder
from services.knowledge.rag.vector_store import RegulationVectorStore
from services.knowledge.rule_engine import RuleEngine
from services.scheduler.polling_jobs import SchedulerJobs
from sqlalchemy import select
from pathlib import Path
import subprocess
import sys
import os

app = FastAPI(title="RegGraph AI API", version="0.1.0")

# CORS middleware must be added first (outermost layer)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware added after CORS (innermost layer, processed first for non-preflight requests)
app.add_middleware(BaseHTTPMiddleware, dispatch=clerk_auth_middleware)


@app.on_event("startup")
async def startup_event() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    graph_builder = ObligationGraphBuilder()
    graph_builder.build_graph()
    app.state.obligation_graph = graph_builder.graph
    app.state.graph_builder = graph_builder
    
    # Resolve chroma_db path relative to repo root (works in Docker with PYTHONPATH=/app)
    repo_root = Path(__file__).resolve().parent.parent.parent
    persist_dir = repo_root / "chroma_db"
    persist_dir.mkdir(exist_ok=True)
    
    vector_store = None
    try:
        vector_store = RegulationVectorStore(str(persist_dir))
        app.state.vector_store = vector_store
    except Exception as e:
        print(f"WARNING: Vector store initialization failed: {e}")
        app.state.vector_store = None
    
    rule_engine = RuleEngine()
    app.state.rule_engine = rule_engine
    
    app.state.ws_manager = manager
    
    scheduler_jobs = SchedulerJobs(graph_builder, manager)
    scheduler_jobs.start()
    app.state.scheduler = scheduler_jobs

    # Auto-seed database if empty
    business_count = 0
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Business))
        businesses = result.scalars().all()
        business_count = len(businesses)
        if not businesses:
            seed_script = repo_root / "data" / "seed" / "seed_db.py"
            if seed_script.exists():
                env = os.environ.copy()
                env.setdefault("SYNC_DATABASE_URL", env.get("DATABASE_URL", ""))
                try:
                    subprocess.run([sys.executable, str(seed_script)], check=False, env=env)
                    result = await session.execute(select(Business))
                    businesses = result.scalars().all()
                    business_count = len(businesses)
                except Exception as e:
                    print(f"WARNING: Seed script failed: {e}")

    reg_count = vector_store.collection.count() if vector_store else 0
    print(f"RGAI Backend initialized. Graph nodes: {graph_builder.graph.number_of_nodes()}. Regulations embedded: {reg_count}. Businesses: {business_count}.")


app.include_router(compliance_router)
app.include_router(obligations_router)
app.include_router(payroll_router)
app.include_router(gst_router)
app.include_router(hitl_router)
app.include_router(audit_router)
app.include_router(assistant_router)
app.include_router(admin_router)
app.include_router(knowledge_router)
app.include_router(demo_router)
app.include_router(websocket_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


app.mount("/static", StaticFiles(directory="."), name="static")
