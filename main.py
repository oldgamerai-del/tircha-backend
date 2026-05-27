from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os, logging

load_dotenv()  # loads your .env file safely

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Tircha backend starting...")
    yield
    logging.info("Shutting down.")

app = FastAPI(title="Tircha API", lifespan=lifespan)

# Security: only allow your frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tircha.com",
        "https://www.tircha.com",
        "http://localhost:3000"  # for local testing only
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "site": "tircha.com"}

@app.get("/api/keywords/{niche}")
async def get_keywords(niche: str):
    # Keyword discovery - never exposes your API keys to frontend
    api_key = os.getenv("OPENROUTER_API_KEY")  # reads from .env safely
    # ... keyword logic here
    return {"niche": niche, "keywords": []}