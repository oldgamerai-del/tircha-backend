"""
Tircha SaaS API — Paid endpoint for creators and writers
Charges via Lemon Squeezy, validates API keys, returns blog content
"""

import os
import hashlib
import json
import time
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import aiohttp
import asyncio

# Simple in-memory API key store
# In production: use a database
VALID_API_KEYS = {
    # "key": {"plan": "starter", "requests_today": 0, "last_reset": timestamp}
}

PLANS = {
    "starter": {"daily_limit": 10,  "price": "$29/mo"},
    "pro":     {"daily_limit": 50,  "price": "$49/mo"},
    "agency":  {"daily_limit": 200, "price": "$99/mo"},
}

app = FastAPI(
    title="Tircha API",
    description="AI Blog Generation API for Creators",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class BlogRequest(BaseModel):
    keyword: str
    niche: Optional[str] = "general"
    length: Optional[str] = "medium"  # short/medium/long


class KeywordRequest(BaseModel):
    seed: str
    niche: Optional[str] = "general"
    limit: Optional[int] = 20


def validate_api_key(api_key: str) -> dict:
    """Validate API key and check rate limits"""
    if not api_key or api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key. Get one at tircha.com/pricing")

    key_data = VALID_API_KEYS[api_key]
    plan = key_data["plan"]
    limit = PLANS[plan]["daily_limit"]

    # Reset daily counter if it's a new day
    today = int(time.time() / 86400)
    if key_data.get("last_reset") != today:
        key_data["requests_today"] = 0
        key_data["last_reset"] = today

    if key_data["requests_today"] >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily limit of {limit} requests reached. Upgrade at tircha.com/pricing"
        )

    return key_data


@app.get("/")
async def root():
    return {
        "name": "Tircha API",
        "version": "1.0",
        "docs": "/docs",
        "pricing": "https://tircha.com/pricing",
        "endpoints": {
            "generate_blog": "POST /api/blog/generate",
            "keyword_research": "POST /api/keywords/research",
            "health": "GET /health"
        }
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/blog/generate")
async def generate_blog(
    request: BlogRequest,
    x_api_key: str = Header(..., description="Your Tircha API key")
):
    """
    Generate a full SEO blog post for any keyword.

    Returns: title, meta_description, content, faq, word_count

    Pricing: tircha.com/pricing
    """
    key_data = validate_api_key(x_api_key)

    if len(request.keyword) < 3:
        raise HTTPException(status_code=400, detail="Keyword must be at least 3 characters")

    # Word count based on plan
    word_targets = {"short": 600, "medium": 900, "long": 1400}
    target_words = word_targets.get(request.length, 900)

    prompt = f"""Write a complete SEO blog article about: "{request.keyword}"

Requirements:
- {target_words}+ words
- Natural conversational tone
- ## H2 headings (keep them short, max 6 words each)
- ### H3 subheadings where needed
- FAQ section at the end with 3 questions
- Niche: {request.niche}
- Start with: "This post contains affiliate links."

Write the full article in markdown:"""

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    models = [
        "openrouter/owl-alpha",
        "openai/gpt-oss-120b:free",
        "google/gemma-4-31b-it:free",
    ]

    content = None
    model_used = None

    async with aiohttp.ClientSession() as session:
        for model in models:
            try:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
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
                        if raw and len(raw) > 200:
                            import re
                            raw = re.sub(r'<think>[\s\S]*?</think>', '', raw).strip()
                            content = raw
                            model_used = data.get("model", model)
                            break
            except Exception:
                continue

    if not content:
        raise HTTPException(status_code=503, detail="Generation failed. Please retry.")

    # Track usage
    key_data["requests_today"] += 1

    import re
    word_count = len(content.split())
    title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    title = title_match.group(1) if title_match else request.keyword.title()

    return {
        "success": True,
        "keyword": request.keyword,
        "title": title,
        "meta_description": f"Complete guide about {request.keyword} for 2026."[:160],
        "content_markdown": content,
        "word_count": word_count,
        "model_used": model_used,
        "requests_remaining": PLANS[key_data["plan"]]["daily_limit"] - key_data["requests_today"],
        "plan": key_data["plan"]
    }


@app.post("/api/keywords/research")
async def keyword_research(
    request: KeywordRequest,
    x_api_key: str = Header(..., description="Your Tircha API key")
):
    """
    Get profitable keyword ideas for any seed topic.

    Returns: list of keywords with intent and difficulty scores
    """
    key_data = validate_api_key(x_api_key)

    import urllib.parse
    suggestions = []

    async with aiohttp.ClientSession() as session:
        prefixes = ["best", "top", "how to", "vs", "review", "free", "cheap", ""]
        for prefix in prefixes[:4]:
            query = f"{prefix} {request.seed}".strip()
            url = f"https://suggestqueries.google.com/complete/search?output=toolbar&q={urllib.parse.quote(query)}&hl=en"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        text = await r.text()
                        import re
                        found = re.findall(r'data="([^"]+)"', text)
                        suggestions.extend(found)
                await asyncio.sleep(0.3)
            except Exception:
                continue

    # Score and deduplicate
    seen = set()
    results = []
    commercial_signals = ["best", "top", "review", "vs", "alternative", "cheap", "buy"]
    info_signals = ["how", "what", "why", "guide", "tutorial"]

    for kw in suggestions:
        if kw in seen or len(kw) < 5:
            continue
        seen.add(kw)

        kw_lower = kw.lower()
        if any(s in kw_lower for s in commercial_signals):
            intent = "commercial"
            score = 85
        elif any(s in kw_lower for s in info_signals):
            intent = "informational"
            score = 65
        else:
            intent = "navigational"
            score = 50

        difficulty = "low" if len(kw.split()) >= 4 else "medium" if len(kw.split()) == 3 else "high"

        results.append({
            "keyword": kw,
            "intent": intent,
            "difficulty": difficulty,
            "opportunity_score": score
        })

    results.sort(key=lambda x: x["opportunity_score"], reverse=True)

    key_data["requests_today"] += 1

    return {
        "success": True,
        "seed": request.seed,
        "keywords": results[:request.limit],
        "total_found": len(results),
        "requests_remaining": PLANS[key_data["plan"]]["daily_limit"] - key_data["requests_today"]
    }


@app.post("/webhooks/lemonsqueezy")
async def lemonsqueezy_webhook(request: Request):
    """
    Lemon Squeezy sends events here when someone subscribes or cancels.
    Automatically creates/revokes API keys.
    """
    body = await request.json()
    event = body.get("meta", {}).get("event_name", "")
    data = body.get("data", {})

    customer_email = data.get("attributes", {}).get("user_email", "")
    product_name = data.get("attributes", {}).get("product_name", "")

    # Determine plan
    plan = "starter"
    if "pro" in product_name.lower():
        plan = "pro"
    elif "agency" in product_name.lower():
        plan = "agency"

    if event == "subscription_created" or event == "subscription_resumed":
        # Generate API key for new subscriber
        api_key = "tircha_" + hashlib.sha256(
            f"{customer_email}{time.time()}".encode()
        ).hexdigest()[:32]

        VALID_API_KEYS[api_key] = {
            "plan": plan,
            "email": customer_email,
            "requests_today": 0,
            "last_reset": int(time.time() / 86400)
        }

        print(f"New subscriber: {customer_email} → {plan} → key: {api_key}")
        # In production: email the API key to customer_email

    elif event == "subscription_cancelled" or event == "subscription_expired":
        # Remove API key
        to_remove = [k for k, v in VALID_API_KEYS.items() if v.get("email") == customer_email]
        for key in to_remove:
            del VALID_API_KEYS[key]
        print(f"Cancelled: {customer_email}")

    return {"received": True}