# main.py
# The main FastAPI application — entry point

import re
import logging
import time
from datetime import datetime
from collections import defaultdict

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from auth import validate_api_key, create_session_token
from search import search_sector_data, format_results_for_prompt
from analyzer import generate_analysis

# ─────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Rate limiter (uses client IP address)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="🇮🇳 India Trade Opportunities API",
    description="""
## Overview
Analyze trade opportunities for specific sectors in India.

## How to Use
1. Get your API key (use `demo-key-123` for testing)
2. Call `GET /session` with your API key to get a session
3. Call `GET /analyze/{sector}` with your API key

## Valid API Keys (for demo)
- `demo-key-123`
- `test-key-456`

## Example Sectors
pharmaceuticals, technology, agriculture, textiles, automotive, energy
    """,
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach rate limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ─────────────────────────────────────────
# IN-MEMORY STORAGE
# ─────────────────────────────────────────
# Stores session info and usage stats per user
sessions_store: dict = {}         # session_id → session data
usage_store: dict = defaultdict(list)  # username → list of request timestamps
cache_store: dict = {}            # sector → cached report


# ─────────────────────────────────────────
# INPUT VALIDATION HELPER
# ─────────────────────────────────────────
VALID_SECTOR_PATTERN = re.compile(r"^[a-zA-Z\s\-]{3,50}$")

def validate_sector(sector: str) -> str:
    """
    Validates sector name:
    - Only letters, spaces, hyphens
    - Between 3 and 50 characters
    """
    sector = sector.strip().lower()
    if not VALID_SECTOR_PATTERN.match(sector):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid sector name. Use only letters (3-50 chars). Example: 'pharmaceuticals'",
        )
    return sector


# ─────────────────────────────────────────
# ROUTE 1: Health Check
# ─────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    """Check if the API is running."""
    return {
        "status": "running",
        "message": "India Trade Opportunities API is live!",
        "docs": "/docs",
        "example": "/analyze/pharmaceuticals",
    }


# ─────────────────────────────────────────
# ROUTE 2: Get Session Token
# ─────────────────────────────────────────
@app.get("/session", tags=["Auth"])
async def get_session(username: str = Depends(validate_api_key)):
    """
    Provide your API key in the X-API-Key header.
    Returns a JWT session token and session metadata.
    """
    session = create_session_token(username)
    sessions_store[session["session_id"]] = {
        **session,
        "created_at": datetime.utcnow().isoformat(),
        "requests_made": 0,
    }
    logger.info(f"New session created for user: {username}")
    return {
        "message": "Session created successfully",
        "session": session,
    }


# ─────────────────────────────────────────
# ROUTE 3: MAIN ENDPOINT — Analyze Sector
# ─────────────────────────────────────────
@app.get(
    "/analyze/{sector}",
    tags=["Analysis"],
    response_class=PlainTextResponse,
    summary="Get trade opportunities report for a sector",
)
@limiter.limit("5/minute")   # Max 5 requests per minute per IP
async def analyze_sector(
    request: Request,
    sector: str,
    username: str = Depends(validate_api_key),
    use_cache: bool = True,
):
    """
    ## Main Endpoint

    Returns a **Markdown-formatted** trade opportunities report for the given sector.

    ### Parameters
    - **sector**: Industry sector name (e.g., `pharmaceuticals`, `technology`, `agriculture`)
    - **use_cache**: Use cached result if available (default: true)

    ### Headers Required
    - `X-API-Key`: Your API key (e.g., `demo-key-123`)

    ### Example
    ```
    GET /analyze/pharmaceuticals
    X-API-Key: demo-key-123
    ```
    """
    # Step 1: Validate sector input
    clean_sector = validate_sector(sector)
    logger.info(f"[{username}] Analyzing sector: {clean_sector}")

    # Step 2: Track usage per user
    now = time.time()
    usage_store[username].append(now)
    # Keep only last hour of timestamps
    usage_store[username] = [t for t in usage_store[username] if now - t < 3600]
    requests_this_hour = len(usage_store[username])

    # Step 3: Check cache (avoid redundant AI calls)
    cache_key = clean_sector
    if use_cache and cache_key in cache_store:
        cached = cache_store[cache_key]
        age_minutes = (now - cached["timestamp"]) / 60
        if age_minutes < 30:  # Cache valid for 30 minutes
            logger.info(f"Returning cached report for: {clean_sector}")
            return PlainTextResponse(
                content=cached["report"],
                media_type="text/markdown",
                headers={
                    "X-Cache": "HIT",
                    "X-Cache-Age-Minutes": str(round(age_minutes, 1)),
                    "X-Requests-This-Hour": str(requests_this_hour),
                },
            )

    # Step 4: Search for current market data
    try:
        logger.info(f"Searching web for sector: {clean_sector}")
        search_results = search_sector_data(clean_sector)
        formatted_data = format_results_for_prompt(search_results)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        formatted_data = "Web search unavailable. Use training knowledge only."

    # Step 5: Generate AI analysis via Gemini
    try:
        logger.info(f"Generating AI analysis for: {clean_sector}")
        report = await generate_analysis(clean_sector, formatted_data)
    except ValueError as e:
        # Missing API key
        raise HTTPException(status_code=503, detail=str(e))
    except RuntimeError as e:
        # Gemini call failed
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error during analysis.")

    # Step 6: Cache the result
    cache_store[cache_key] = {
        "report": report,
        "timestamp": now,
        "generated_by": username,
    }

    logger.info(f"[{username}] Report generated successfully for: {clean_sector}")

    return PlainTextResponse(
        content=report,
        media_type="text/markdown",
        headers={
            "X-Cache": "MISS",
            "X-Sector": clean_sector,
            "X-Requests-This-Hour": str(requests_this_hour),
        },
    )


# ─────────────────────────────────────────
# ROUTE 4: Usage Stats
# ─────────────────────────────────────────
@app.get("/stats", tags=["Monitoring"])
async def get_stats(username: str = Depends(validate_api_key)):
    """Returns your API usage stats and cache info."""
    now = time.time()
    recent = [t for t in usage_store[username] if now - t < 3600]
    return {
        "username": username,
        "requests_last_hour": len(recent),
        "cached_sectors": list(cache_store.keys()),
        "active_sessions": len(sessions_store),
    }


# ─────────────────────────────────────────
# RUN THE SERVER
# ─────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
