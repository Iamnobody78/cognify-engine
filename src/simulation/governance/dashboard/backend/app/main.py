"""FastAPI application entrypoint for the MCP monitoring dashboard."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import init_db
from .routers import health, hypotheses, usage

app = FastAPI(
    title="MCP Governance Dashboard",
    version="1.0.0",
    description="Real-time MCP server health, tool latency, and hypothesis hit-rate monitoring.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only; tighten for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(usage.router)
app.include_router(hypotheses.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/api/ping")
def ping() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8010, reload=False)
