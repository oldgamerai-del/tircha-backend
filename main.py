from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Tircha backend starting...")
    # Initialize the API keys database
    try:
        from api_routes import init_db
        init_db()
        logger.info("API database initialized")
    except Exception as e:
        logger.error(f"DB init failed: {e}")
    yield
    logger.info("Shutting down.")

app = FastAPI(
    title="Tircha API",
    description="AI Blog Generation API + Affiliate Content Engine",
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

# ── Core routes ─────────────────────────────────────────────
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

# ── Mount all SaaS API routes ────────────────────────────────
try:
    from api_routes import (
        generate_blog,
        keyword_research,
        razorpay_webhook,
        create_test_key,
        BlogRequest,
        KeywordRequest
    )

    app.post("/api/blog/generate")(generate_blog)
    app.post("/api/keywords/research")(keyword_research)
    app.post("/webhooks/razorpay")(razorpay_webhook)
    app.post("/admin/create-key")(create_test_key)

    logger.info("SaaS API routes loaded successfully")
except Exception as e:
    logger.error(f"Failed to load API routes: {e}")
