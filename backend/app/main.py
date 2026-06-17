"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="Evidence-Grounded Interview Feedback Synthesis Copilot. "
    "Surfaces evidence. Human decides.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers will be included here as they are built
# from app.routers import projects, extract, analyze, synthesize, review
# app.include_router(projects.router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    """Health check. Returns service status and version."""
    return {
        "status": "ok",
        "version": settings.app_version,
        "llm_mode": "mock" if settings.llm_mock_mode else ("baseline" if settings.baseline_mode else "llm"),
    }


@app.get("/", tags=["system"])
async def root() -> dict:
    return {"message": "Interview Feedback Copilot API", "docs": "/docs"}
