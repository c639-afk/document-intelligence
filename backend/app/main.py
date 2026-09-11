from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.database import Base, engine
from app.api.routes.documents import router as documents_router

from app.core.logging import configure_logging

configure_logging()
# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------

Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------
# APP
# ---------------------------------------------------------

app = FastAPI(
    title="Document Intelligence API",
    version="1.0.0",
    description=(
        "End-to-end document intelligence platform for extracting "
        "financial information from PDF, JPG, and PNG documents, "
        "performing financial validation, and persisting processed results."
    ),
    openapi_tags=[
        {
            "name": "Documents",
            "description": (
                "Upload, process, retrieve, and list financial documents."
            ),
        },
        {
            "name": "Health",
            "description": "Service health and availability checks.",
        },
    ],
)


# ---------------------------------------------------------
# API ROUTES
# ---------------------------------------------------------

app.include_router(
    documents_router,
    prefix="/api/v1",
)


@app.get(
    "/api/v1/health",
    tags=["Health"],
    summary="Check API health",
    description="Returns the current health status of the Document Intelligence API.",
)
def health_check():
    return {
        "status": "healthy",
        "service": "document-intelligence-api",
    }


# ---------------------------------------------------------
# FRONTEND
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR / "static"),
    name="static",
)


@app.get("/")
def serve_frontend():
    return FileResponse(
        FRONTEND_DIR / "templates" / "index.html"
    )