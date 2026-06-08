import os
import hashlib
import hmac as hmac_lib
import json
import time
import sqlite3
import secrets
import asyncio
import re
import urllib.parse
import aiohttp
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

DB_PATH = os.getenv("DATABASE_PATH", "./tircha_api.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            plan TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            requests_today INTEGER DEFAULT 0,
            last_reset TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT,
            endpoint TEXT,
            keyword TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

PLANS = {
    "starter": 10,
    "pro":     50,
    "agency":  200,
}

def get_key_data(api_key: str) -> dict:
    if not api_key or not api_key.startswith("tircha_"):
        raise HTTPException(
            status_code=401,
            detail="Invalid API key. Get yours at tircha.com/pricing"
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM api_keys WHERE api_key = ?", (api_key,)
    ).fetchone()

    if not row:
        conn.close()
        raise HTTPException(
            status_code=401,
            detail="API key not found. Subscribe at tircha.com/pricing"
        )
    if row["status"] != "active":
        conn.close()
        raise HTTPException(
            status_code=403,
            detail="Subscription inactive. Renew at tircha.com/pricing"
        )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if row["last_reset"] != today:
        conn.execute(
            "UPDATE api_keys SET requests_today=0, last_reset=? WHERE api_key=?",
            (today, api_key)
        )
        conn.commit()
        requests_today = 0
    else:
        requests_today = row["requests_today"]

    limit = PLANS.get(row["plan"], 10)
    if requests_today >= limit:
        conn.close()
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of {limit} reached. Upgrade at tircha.com/pricing"
        )

    data = dict(row)
    data["requests_today"] = requests_today
    data["limit"] = limit
    conn.close()
    return data

def increment_usage(api_key: str, endpoint: str, keyword: str = ""):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE api_keys SET requests_today=requests_today+1 WHERE api_key=?",
        (api_key,)
    )
    conn.execute(
        "INSERT INTO usage_log (api_key, endpoint, keyword) VALUES (?,?,?)",
        (api_key, endpoint, keyword)
    )
    conn.commit()
    conn.close()

class BlogRequest(BaseModel):
    keyword: str
    niche: Optional[str] = "general"
    length: Optional[str] = "medium"

class KeywordRequest(BaseModel):
    seed: str
    niche: Optional[str] = "general"
    limit: Optional[int] = 20


@router.post("/api/blog/generate")
async def generate_blog(
    request: BlogRequest,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    key_data = get_key_data(x_api_key)

    if len(request.keyword.strip()) < 3:
        raise HTTPException(status_code=400, detail="Keyword too short")

    word_targets = {"short": 600, "medium": 900, "long": 1400}
    target_words = word_targets.get(request.length, 900)

    prompt = f"""Write a complete SEO blog article about: "{request.keyword}"

Requirements:
- {target_words}+ words minimum, do not stop early
- Natural conversational tone
- Short ## H2 headings, max 6 words each
- ### H3 subheadings where helpful
- FAQ section at end with 3 questions
- Niche: {request.niche}
- Start with: "This post contains affiliate links."

Write the full article in markdown now:"""

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    models = [
        "openrouter/owl-alpha",
        "openai/gpt-oss-120b:free",
        "google/gemma-4-31b-it:free",
        "z-ai/glm-4.5-air:free",
    ]

    content = None
    model_used = None

    async with aiohttp.ClientSession() as session:
        for model in models:
            try:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {openrouter_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://tircha.com",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 2000,
                        "temperature": 0.7
                    },
                    timeout=aiohttp.ClientTimeout(total=90)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        msg = data["choices"][0]["message"]
                        raw = msg.get("content") or msg.get("reasoning_content") or ""
                        raw = re.sub(r'<think>[\s\S]*?</think>', '', raw).strip()
                        if raw and len(raw) > 200:
                            content = raw
                            model_used = data.get("model", model)
                            break
            except Exception:
                continue

    if not content:
        raise HTTPException(status_code=503, detail="Generation failed. Please retry.")

    increment_usage(x_api_key, "blog/generate", request.keyword)

    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_match.group(1) if title_match else request.keyword.title()

    return {
        "success": True,
        "keyword": request.keyword,
        "title": title,
        "meta_description": f"Expert guide about {request.keyword} for 2026."[:160],
        "content_markdown": content,
        "word_count": len(content.split()),
        "requests_used": key_data["requests_today"] + 1,
        "requests_remaining": key_data["limit"] - key_data["requests_today"] - 1,
        "plan": key_data["plan"]
    }


@router.post("/api/keywords/research")
async def keyword_research(
    request: KeywordRequest,
    x_api_key: str = Header(..., alias="X-API-Key")
):
    key_data = get_key_data(x_api_key)
    suggestions = []

    async with aiohttp.ClientSession() as session:
        for prefix in ["best", "top", "how to", "vs", ""]:
            query = f"{prefix} {request.seed}".strip()
            url = f"https://suggestqueries.google.com/complete/search?output=toolbar&q={urllib.parse.quote(query)}&hl=en"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        text = await r.text()
                        found = re.findall(r'data="([^"]+)"', text)
                        suggestions.extend(found)
                await asyncio.sleep(0.3)
            except Exception:
                continue

    seen = set()
    results = []
    for kw in suggestions:
        if kw in seen or len(kw) < 5:
            continue
        seen.add(kw)
        kw_lower = kw.lower()
        intent = "commercial" if any(w in kw_lower for w in ["best","top","review","vs","buy"]) else "informational"
        difficulty = "low" if len(kw.split()) >= 4 else "medium" if len(kw.split()) == 3 else "high"
        results.append({
            "keyword": kw,
            "intent": intent,
            "difficulty": difficulty,
            "opportunity_score": 85 if intent == "commercial" else 60
        })

    results.sort(key=lambda x: x["opportunity_score"], reverse=True)
    increment_usage(x_api_key, "keywords/research", request.seed)

    return {
        "success": True,
        "seed": request.seed,
        "keywords": results[:request.limit],
        "total_found": len(results),
        "requests_remaining": key_data["limit"] - key_data["requests_today"] - 1,
        "plan": key_data["plan"]
    }


@router.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    secret = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    if secret and signature:
        expected = hmac_lib.new(
            secret.encode(), body, hashlib.sha256
        ).hexdigest()
        if not hmac_lib.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    data = json.loads(body)
    event = data.get("event", "")
    payload = data.get("payload", {})
    subscription = payload.get("subscription", {}).get("entity", {})
    email = subscription.get("email", "")
    plan_id = subscription.get("plan_id", "")

    PLAN_MAP = {
        os.getenv("RAZORPAY_STARTER_PLAN_ID", ""): "starter",
        os.getenv("RAZORPAY_PRO_PLAN_ID", ""):     "pro",
        os.getenv("RAZORPAY_AGENCY_PLAN_ID", ""):  "agency",
    }
    plan = PLAN_MAP.get(plan_id, "starter")

    conn = sqlite3.connect(DB_PATH)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if event in ("subscription.activated", "subscription.charged"):
        existing = conn.execute(
            "SELECT api_key FROM api_keys WHERE email=?", (email,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE api_keys SET status='active', plan=? WHERE email=?",
                (plan, email)
            )
            api_key = existing[0]
        else:
            api_key = "tircha_" + secrets.token_hex(24)
            conn.execute(
                "INSERT INTO api_keys (api_key,email,plan,status,last_reset) VALUES (?,?,?,'active',?)",
                (api_key, email, plan, today)
            )
        conn.commit()
        conn.close()
        print(f"SUBSCRIBER: {email} plan={plan} key={api_key}")

    elif event in ("subscription.cancelled", "subscription.completed", "subscription.halted"):
        conn.execute(
            "UPDATE api_keys SET status='inactive' WHERE email=?", (email,)
        )
        conn.commit()
        conn.close()

    return {"received": True}


@router.post("/admin/create-key")
async def create_test_key(
    email: str,
    plan: str = "starter",
    x_admin_secret: str = Header(..., alias="X-Admin-Secret")
):
    admin_secret = os.getenv("ADMIN_SECRET", "")
    if not admin_secret or x_admin_secret != admin_secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    api_key = "tircha_" + secrets.token_hex(24)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO api_keys (api_key,email,plan,status,last_reset) VALUES (?,?,?,'active',?)",
        (api_key, email, plan, today)
    )
    conn.commit()
    conn.close()
    return {"api_key": api_key, "email": email, "plan": plan}
