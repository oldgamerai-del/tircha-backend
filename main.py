from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os
import logging
import sys
import traceback

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from api_routes import router as api_router
    from api_routes import init_db
    logger.info("Successfully imported api_routes")
except Exception as e:
    logger.error(f"Failed to import api_routes: {e}")
    logger.error(traceback.format_exc())
    sys.exit(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Tircha backend starting...")
    init_db()
    logger.info("Database ready")
    yield
    logger.info("Shutting down.")

app = FastAPI(
    title="Tircha API",
    description="AI Blog Generation API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tircha.com",
        "https://www.tircha.com",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "name": "Tircha Backend API",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health():
    return {"status": "ok", "site": "tircha.com"}

@app.get("/debug/routes")
async def debug_routes():
    return {"routes": [route.path for route in app.routes]}

app.include_router(api_router)
logger.info(f"Registered {len(app.routes)} routes")
