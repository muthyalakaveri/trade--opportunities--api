# analyzer.py
import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


def build_prompt(sector: str, search_data: str) -> str:
    short_data = search_data[:1000]
    return f"""You are a trade analyst for Indian markets.
Analyze the {sector} sector in India and write a markdown report with:

# India {sector.title()} - Trade Opportunities Report

## Market Overview
## Top 3 Trade Opportunities
## Key Challenges
## Recommendations

Use this data if helpful: {short_data}
Keep report under 500 words."""


async def generate_analysis(sector: str, search_data: str) -> str:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not configured in .env file")

    try:
        prompt = build_prompt(sector, search_data)
        logger.info(f"Sending request to Groq for sector: {sector}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 1000
                },
                timeout=30.0
            )
            data = response.json()
            logger.info(f"Groq raw response: {data}")
            if "choices" not in data:
                raise RuntimeError(f"Groq error: {data}")
            report = data["choices"][0]["message"]["content"]
            logger.info(f"Groq response received, length: {len(report)} chars")
            return report

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        raise RuntimeError(f"AI analysis failed: {str(e)}")