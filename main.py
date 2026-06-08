from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os
import logging
import sys

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

print("MAIN.PY STARTING", flush=True)
logger.info("MAIN.PY STARTING")

# Test imports step by step
print("About to import api_routes", flush=True)
try:
    import api_routes
    print("api_routes imported successfully", flush=True)
    logger.info("api_routes imported successfully")
except Exception as e:
    print(f"ERROR importing api_routes: {e}", flush=True)
    logger.error(f"ERROR importing api_routes: {e}", exc_info=True)
    raise

router = api_routes.router
init_db = api_routes.init_db

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
    routes = []
    for route in app.routes:
        route_info = {
            "path": route.path,
            "methods": list(route.methods) if hasattr(route, "methods") else []
        }
        routes.append(route_info)
    return {"total": len(routes), "routes": routes}

print(f"About to include router with {len(router.routes)} routes", flush=True)
app.include_router(router)
print(f"Router included. Total app routes now: {len(app.routes)}", flush=True)
logger.info(f"Router included. Total app routes: {len(app.routes)}")
