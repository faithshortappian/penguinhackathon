"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.health_routes import router as health_router
from app.ai_routes import router as ai_router
from app.compat_routes import router as compat_router

app = FastAPI(
    title="Appian AI Context Service",
    description="Backend for providing AI-powered SAIL code assistance to the Appian browser extension",
    version="0.2.0",
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


@app.get("/health")
async def health():
    return {"status": "ok"}
