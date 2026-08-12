"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.health_routes import router as health_router
from app.ai_routes import router as ai_router
from app.compat_routes import router as compat_router
from app.parser_routes import router as parser_router
from app.context_routes import router as context_router
from app.package_watcher import router as watcher_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load persisted context from disk on startup, watch for new ZIPs."""
    from app.context_store import load_from_disk
    from app.package_watcher import check_for_new_packages
    load_from_disk()
    check_for_new_packages()  # Parse any ZIPs in packages/ folder
    yield


app = FastAPI(
    title="Appian AI Context Service",
    description="Backend for providing AI-powered SAIL code assistance to the Appian browser extension",
    version="0.3.0",
    lifespan=lifespan,
)

# Allow Chrome extension to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health checks (test each connection)
app.include_router(health_router)

# AI processing routes (Bedrock + MCP context)
app.include_router(ai_router)

# Backward-compatible routes for the Chrome extension frontend
app.include_router(compat_router)

# Solutions parser routes (Appian XML → JSON)
app.include_router(parser_router)

# Parsed context query routes (extension reads these)
app.include_router(context_router)

# Package watcher reload route
if watcher_router:
    app.include_router(watcher_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
