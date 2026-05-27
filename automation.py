"""
Tircha Automation Engine
Runs automatically - you never need to touch this after setup
"""
import asyncio, aiohttp, os, json, re, logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

NICHES = {
    "trading": [
        "best trading platform for beginners 2026",
        "TradingView vs Thinkorswim comparison",
        "how to start day trading with $1000",
        "best forex broker low spread",
        "copy trading platforms review 2026",
        "algorithmic trading software free",
        "crypto trading bot comparison",
        "best stock screener software",
        "paper trading platforms review",
        "options trading platform comparison"
    ],
    "ai-tools": [
        "best AI writing tools 2026",
        "ChatGPT vs Claude vs Gemini comparison",
        "free AI tools for students",
        "Jasper AI review 2026",
        "best AI image generator free",
        "AI tools to make money online",
        "best AI coding assistant for beginners",
        "Writesonic vs Jasper comparison",
        "AI tools for content creators",
        "best AI chatbot for customer service"
    ],
    "software": [
        "best VPN for streaming 2026",
        "NordVPN vs ExpressVPN comparison",
        "best web hosting for beginners",
        "Hostinger review 2026",
        "best project management software small team",
        "Monday.com vs Asana comparison",
        "best antivirus software free 2026",
        "Semrush vs Ahrefs which is better",
        "best password manager 2026",
        "cloud storage comparison 2026"
    ],
    "gaming": [
        "best gaming headset under 100 dollars",
        "RTX 4070 vs RX 7800 XT comparison",
        "best gaming monitor 144hz budget",
        "Razer BlackShark V2 review",
        "best gaming chair for long sessions",
        "gaming VPN to reduce ping lag",
        "SteelSeries Arctis Nova Pro review",
        "best mechanical keyboard for gaming",
        "gaming laptop vs desktop which better",
        "best budget gaming PC build 2026"
    ]
}

AFFILIATE_LINKS = {
    "TradingView": os.getenv("TRADINGVIEW_AFFILIATE_URL", ""),
    "eToro": os.getenv("ETORO_AFFILIATE_URL", ""),
    "Jasper": os.getenv("JASPER_AFFILIATE_URL", ""),
    "NordVPN": os.getenv("NORDVPN_AFFILIATE_URL", ""),
    "Hostinger": os.getenv("HOSTINGER_AFFILIATE_URL", ""),
    "Razer": os.getenv("RAZER_AFFILIATE_URL", ""),
    "SteelSeries": os.getenv("STEELSERIES_AFFILIATE_URL", ""),
}

async def generate_article(keyword: str, niche: str) -> dict:
    """Generate one full SEO article using free AI"""
    
    prompt = f"""Write a complete SEO-optimized article for tircha.com about: "{keyword}"

REQUIREMENTS:
- 1500+ words
- Include H2 and H3 headings
- Natural keyword placement throughout  
- FAQ section at end (5 questions)
- Comparison table if relevant
- Clear conclusion with recommendation
- Affiliate disclosure at start: "This post contains affiliate links. We may earn a commission at no extra cost to you."
- Tone: helpful, expert, conversational
- Niche: {niche}

OUTPUT as JSON only:
{{
  "title": "SEO-optimized H1 title",
  "meta_description": "150 char description with keyword",
  "slug": "url-friendly-slug",
  "content_markdown": "full article in markdown",
  "faq": [{{"q": "question", "a": "answer"}}],
  "social_snippet": "tweet-length summary"
}}"""

    api_key = os.getenv("OPENROUTER_API_KEY")
    
    async with aiohttp.ClientSession() as session:
        for model in [
            "mistralai/mistral-7b-instruct:free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "google/gemma-2-9b-it:free"
        ]:
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
                        "max_tokens": 4000,
                        "temperature": 0.7
                    },
                    timeout=aiohttp.ClientTimeout(total=90)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        raw = data["choices"][0]["message"]["content"]
                        # Clean and parse JSON
                        clean = re.sub(r'```json\n?|\n?```', '', raw).strip()
                        match = re.search(r'\{[\s\S]*\}', clean)
                        if match:
                            article = json.loads(match.group())
                            # Inject affiliate links
                            content = article.get("content_markdown", "")
                            for product, link in AFFILIATE_LINKS.items():
                                if product.lower() in content.lower() and link:
                                    content = content.replace(
                                        product, 
                                        f"[{product}]({link})",
                                        1  # only first mention
                                    )
                            article["content_markdown"] = content
                            article["niche"] = niche
                            article["generated_at"] = datetime.utcnow().isoformat()
                            article["keyword"] = keyword
                            logging.info(f"✅ Generated: {article.get('title', keyword)}")
                            return article
            except Exception as e:
                logging.error(f"Model {model} failed: {e}")
                continue
    
    return {}

async def save_article(article: dict):
    """Save article as markdown file for Vercel to pick up"""
    if not article or not article.get("slug"):
        return
    
    slug = article["slug"]
    # Works on both your Windows machine AND Railway server
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    BLOG_DIR = os.path.join(BASE_DIR, "frontend", "content", "blog")

    os.makedirs(BLOG_DIR, exist_ok=True)
    filepath = os.path.join(BLOG_DIR, f"{slug}.json")
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(article, f, indent=2, ensure_ascii=False)
    
    logging.info(f"📄 Saved: {filepath}")

async def run_daily_batch():
    """Generate 6 articles per day, one per keyword"""
    logging.info("🚀 Starting daily content batch...")
    
    import random
    # Pick 6 random keywords from all niches
    all_keywords = []
    for niche, keywords in NICHES.items():
        for kw in keywords:
            all_keywords.append((kw, niche))
    
    batch = random.sample(all_keywords, min(6, len(all_keywords)))
    
    for keyword, niche in batch:
        article = await generate_article(keyword, niche)
        if article:
            await save_article(article)
        await asyncio.sleep(15)  # wait between articles
    
    logging.info("✅ Daily batch complete!")

if __name__ == "__main__":
    asyncio.run(run_daily_batch())