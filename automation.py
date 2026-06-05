import asyncio
import aiohttp
import json
import re
import os
import random
import logging
from datetime import datetime, timezone
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

PROJECT_DIR = os.path.dirname(BASE_DIR)
BLOG_DIR = os.path.join(PROJECT_DIR, "content", "blog")
os.makedirs(BLOG_DIR, exist_ok=True)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

FREE_MODELS = [
    "openrouter/owl-alpha",                      # Best - 1M context, always free
    "openai/gpt-oss-120b:free",                  # OpenAI quality, free
    "google/gemma-4-31b-it:free",                # Google Gemma 4, reliable
    "nvidia/nemotron-3-super-120b-a12b:free",    # Nvidia 1M context
    "z-ai/glm-4.5-air:free",                     # Fast fallback
    "openai/gpt-oss-20b:free",                   # Lightweight fallback
    "google/gemma-4-26b-a4b-it:free",            # Final fallback
]
MODEL_INDEX = 0  # rotates on each run

NICHES = {
    "trading": [
        "best trading platform for beginners 2026",
        "TradingView vs Thinkorswim comparison",
        "how to start day trading with $1000",
        "best forex broker for beginners 2026",
        "copy trading platforms review 2026",
        "best crypto trading bots 2026",
        "eToro review 2026 is it safe",
        "best stock screener tools 2026",
        "algorithmic trading software for beginners",
        "best paper trading platforms free",
    ],
    "ai-tools": [
        "best AI writing tools 2026",
        "ChatGPT vs Claude vs Gemini comparison 2026",
        "free AI tools for students 2026",
        "Jasper AI review 2026",
        "best AI image generator free 2026",
        "best AI tools to make money online",
        "Writesonic vs Jasper which is better",
        "best AI coding assistant for beginners",
        "Claude AI vs ChatGPT which is better",
        "best AI tools for content creators",
    ],
    "software": [
        "best VPN for streaming 2026",
        "NordVPN vs ExpressVPN comparison 2026",
        "best web hosting for beginners 2026",
        "Hostinger review 2026",
        "best password manager 2026",
        "Monday.com vs Asana comparison",
        "best antivirus software free 2026",
        "Semrush vs Ahrefs which is better 2026",
        "best cloud storage free 2026",
        "Grammarly review 2026 is it worth it",
    ],
    "gaming": [
        "best gaming headset under 100 dollars 2026",
        "best budget gaming monitor 2026",
        "Razer BlackShark V2 review 2026",
        "best mechanical keyboard for gaming 2026",
        "gaming laptop vs desktop which is better",
        "best gaming chair under 300 dollars",
        "SteelSeries Arctis Nova review 2026",
        "best gaming VPN to reduce ping",
        "RTX 4070 vs RX 7800 XT comparison",
        "best budget gaming PC build 2026",
    ]
}

AFFILIATE_LINKS = {
    "TradingView": os.getenv("TRADINGVIEW_AFFILIATE_URL", ""),
    "eToro":       os.getenv("ETORO_AFFILIATE_URL", ""),
    "NordVPN":     os.getenv("NORDVPN_AFFILIATE_URL", ""),
    "Jasper":      os.getenv("JASPER_AFFILIATE_URL", ""),
    "Hostinger":   os.getenv("HOSTINGER_AFFILIATE_URL", ""),
    "Grammarly":   os.getenv("GRAMMARLY_AFFILIATE_URL", ""),
    "Razer":       os.getenv("RAZER_AFFILIATE_URL", ""),
    "SteelSeries": os.getenv("STEELSERIES_AFFILIATE_URL", ""),
    "Writesonic":  os.getenv("WRITESONIC_AFFILIATE_URL", ""),
    "Semrush":     os.getenv("SEMRUSH_AFFILIATE_URL", ""),
}


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text[:80]


def extract_title_from_markdown(content: str, fallback: str) -> str:
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    lines = content.strip().split('\n')
    for line in lines[:5]:
        clean = line.replace('#', '').strip()
        if len(clean) > 15 and not clean.startswith('*'):
            return clean
    return fallback.title()


def extract_faq_from_markdown(content: str) -> list:
    faqs = []
    faq_match = re.search(
        r'#{1,3}\s*(?:FAQ|Frequently Asked Questions?)(.*?)(?=#{1,3}|\Z)',
        content, re.IGNORECASE | re.DOTALL
    )
    if not faq_match:
        return faqs
    faq_text = faq_match.group(1)
    pattern = re.findall(
        r'#{2,4}\s*(.+?)\n(.*?)(?=#{2,4}|\Z)',
        faq_text, re.DOTALL
    )
    for q, a in pattern:
        q = q.strip()
        a = re.sub(r'\s+', ' ', a.strip())
        if len(q) > 5 and len(a) > 10:
            faqs.append({"q": q, "a": a[:400]})
    return faqs[:5]


def inject_affiliate_links(content: str) -> str:
    for product, link in AFFILIATE_LINKS.items():
        if not link:
            continue
        if product.lower() not in content.lower():
            continue
        if f"]({link})" in content:
            continue
        pattern = re.compile(rf"\b{re.escape(product)}\b", re.IGNORECASE)
        content = pattern.sub(f"[{product}]({link})", content, count=1)
    return content


def build_prompt(keyword: str, niche: str) -> str:
    return f"""You are an expert SEO content writer for tircha.com.

Write a detailed, helpful article about: "{keyword}"

REQUIREMENTS:
- Write at least 600 words minimum. Do not stop early.
- Keep writing until you have covered all sections fully.
- Natural human tone
- SEO optimized with keyword in first paragraph
- Use ## H2 and ### H3 markdown headings
- End with a ## FAQ section with exactly 3 questions and answers
- Niche: {niche}

Start the article with this exact line:
*This post contains affiliate links. We may earn a commission at no extra cost to you.*

Write the full article now in plain markdown:"""


def save_article(article: dict) -> bool:
    slug = article.get("slug", "")
    if not slug:
        return False
    filepath = os.path.join(BLOG_DIR, f"{slug}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(article, f, indent=2, ensure_ascii=False)
    logging.info(f"  SAVED: {filepath}")
    return True


async def generate_article(keyword: str, niche: str):
    if not OPENROUTER_API_KEY:
        logging.error("OPENROUTER_API_KEY missing")
        return None

    prompt = build_prompt(keyword, niche)
    logging.info(f"Generating: {keyword}")
    # Rotate models across articles for better rate limit handling
    import time
    model_to_use = FREE_MODELS[int(time.time()) % len(FREE_MODELS)]
    logging.info(f"  Using model: {model_to_use}")
async with aiohttp.ClientSession() as session:
    for attempt in range(len(FREE_MODELS)):
        model = FREE_MODELS[attempt % len(FREE_MODELS)]
        try:
            logging.info(f"  Attempt {attempt + 1} using: {model}")

            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://tircha.com",
                    "X-Title": "Tircha AI Writer"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 1500
                },
                timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                logging.info(f"  Status: {resp.status}")

                if resp.status == 429:
                    logging.warning(f"  Rate limited on {model}, trying next...")
                    await asyncio.sleep(15)
                    continue

                if resp.status == 404:
                    logging.error(f"  Model {model} not found, trying next...")
                    continue

                if resp.status != 200:
                    err = await resp.text()
                    logging.error(f"  Error {resp.status}: {err[:200]}")
                    await asyncio.sleep(10)
                    continue

                data = await resp.json()

                # Handle all response formats including reasoning models
                msg = data["choices"][0]["message"]

                # Try all possible content fields
                content = (
                    msg.get("content") or
                    msg.get("reasoning_content") or
                    msg.get("reasoning") or
                    ""
                )

                # Remove thinking tags that some models add
                if content and "<think>" in content:
                    # Keep content after thinking section
                    after_think = re.sub(r'<think>[\s\S]*?</think>', '', content)
                    content = after_think.strip() if after_think.strip() else content

                if not content or len(content) < 200:
                    logging.warning(f"  Content too short or empty ({len(content) if content else 0} chars)")
                    await asyncio.sleep(10)
                    continue

                content = content.strip()
                model_used = data.get("model", model)
                content = inject_affiliate_links(content)
                title = extract_title_from_markdown(content, keyword)
                faqs = extract_faq_from_markdown(content)
                slug = slugify(keyword)

                article = {
                    "title": title,
                    "meta_description": f"Expert guide: {keyword}. Reviews and recommendations for 2026."[:160],
                    "slug": slug,
                    "content_markdown": content,
                    "faq": faqs,
                    "keyword": keyword,
                    "niche": niche,
                    "model_used": model_used,
                    "word_count": len(content.split()),
                    "generated_at": datetime.now(timezone.utc).isoformat()
                }

                logging.info(f"  SUCCESS via {model_used}: '{title}' ({len(content.split())} words)")
                return article

        except asyncio.TimeoutError:
            logging.error(f"  Timeout with {model}")
            await asyncio.sleep(15)
        except Exception as e:
            logging.error(f"  Exception with {model}: {e}")
            await asyncio.sleep(10)

logging.error(f"FAILED all models for: {keyword}")
return None

async def run_batch():
    logging.info("=" * 60)
    logging.info("Tircha AI Article Generator")
    logging.info(f"Blog folder: {BLOG_DIR}")
    logging.info(f"API key: {OPENROUTER_API_KEY[:12]}..." if OPENROUTER_API_KEY else "NO API KEY")
    logging.info("=" * 60)

    if not OPENROUTER_API_KEY:
        logging.error("Add OPENROUTER_API_KEY to your .env file")
        return

    # 1 article per niche = 4 total per run
    batch = []
    for niche, keywords in NICHES.items():
        pick = random.choice(keywords)
        batch.append((pick, niche))

    logging.info(f"Batch: {len(batch)} articles")
    logging.info("")

    success = 0
    for i, (keyword, niche) in enumerate(batch, 1):
        logging.info(f"[{i}/{len(batch)}] {niche.upper()}: {keyword}")
        article = await generate_article(keyword, niche)
        if article:
            if save_article(article):
                success += 1
        logging.info("")
        if i < len(batch):
            logging.info("Waiting 30s before next article...")
            await asyncio.sleep(30)

    logging.info("=" * 60)
    logging.info(f"COMPLETE: {success}/{len(batch)} articles saved")
    logging.info(f"Folder: {BLOG_DIR}")
    logging.info("=" * 60)

    if os.path.exists(BLOG_DIR):
        files = [f for f in os.listdir(BLOG_DIR) if f.endswith('.json')]
        logging.info(f"Total articles in blog folder: {len(files)}")


if __name__ == "__main__":
    asyncio.run(run_batch())
