from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from api_routes import router as api_router
from api_routes import init_db

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

app.include_router(api_router)