"""Agent 01 — Regulatory Crawler: monitors 160+ regulatory bodies"""
import asyncio
import hashlib
import logging
from datetime import datetime
from typing import Optional
import httpx
import feedparser
from bs4 import BeautifulSoup
from backend.database import AsyncSessionLocal
from backend.models.alert import SourceDocument
from backend.sources.regulatory_sources import REGULATORY_SOURCES
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def fetch_url(client: httpx.AsyncClient, url: str, timeout: int = 30) -> Optional[str]:
    try:
        r = await client.get(url, timeout=timeout, follow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.warning(f"Fetch failed {url}: {e}")
        return None


async def crawl_rss_feed(source: dict, client: httpx.AsyncClient) -> list[dict]:
    """Crawl an RSS/Atom feed and return new documents"""
    content = await fetch_url(client, source["url"])
    if not content:
        return []
    
    feed = feedparser.parse(content)
    documents = []
    for entry in feed.entries[:20]:
        url = entry.get("link", "")
        title = entry.get("title", "")
        summary = entry.get("summary", entry.get("description", ""))
        
        # Strip HTML from summary
        if summary:
            soup = BeautifulSoup(summary, "html.parser")
            summary = soup.get_text(separator=" ", strip=True)
        
        documents.append({
            "source_type": "regulator",
            "source_name": source["name"],
            "url": url,
            "raw_content": f"TITLE: {title}\n\nSUMMARY: {summary}\n\nSOURCE: {source['name']}\nJURISDICTION: {source['jurisdiction']}",
        })
    return documents


async def crawl_webpage(source: dict, client: httpx.AsyncClient) -> list[dict]:
    """Crawl a webpage and extract regulatory content"""
    content = await fetch_url(client, source["url"])
    if not content:
        return []
    
    soup = BeautifulSoup(content, "html.parser")
    
    # Remove navigation and footer
    for tag in soup(["nav", "header", "footer", "script", "style"]):
        tag.decompose()
    
    text = soup.get_text(separator="\n", strip=True)
    text = "\n".join(line for line in text.splitlines() if line.strip())[:5000]
    
    return [{
        "source_type": "regulator",
        "source_name": source["name"],
        "url": source["url"],
        "raw_content": f"SOURCE: {source['name']}\nJURISDICTION: {source['jurisdiction']}\n\n{text}",
    }]


async def save_new_documents(documents: list[dict]) -> int:
    """Save new documents to DB, skip duplicates"""
    saved = 0
    async with AsyncSessionLocal() as db:
        for doc in documents:
            if not doc.get("url") or not doc.get("raw_content"):
                continue
            existing = await db.execute(
                select(SourceDocument).where(SourceDocument.url == doc["url"]))
            if existing.scalar_one_or_none():
                continue
            sd = SourceDocument(**doc)
            db.add(sd)
            saved += 1
        await db.commit()
    return saved


async def crawl_all_regulators():
    """Main entry point — crawl all configured regulatory sources"""
    logger.info(f"Starting regulatory crawl of {len(REGULATORY_SOURCES)} sources")
    total_saved = 0
    
    async with httpx.AsyncClient(
        headers={"User-Agent": "RegWatch-Nexus/7.0 Compliance Intelligence Crawler"},
        timeout=30.0
    ) as client:
        # Process in batches to avoid overloading
        batch_size = 10
        for i in range(0, len(REGULATORY_SOURCES), batch_size):
            batch = REGULATORY_SOURCES[i:i + batch_size]
            tasks = []
            for source in batch:
                if source.get("type") == "rss":
                    tasks.append(crawl_rss_feed(source, client))
                else:
                    tasks.append(crawl_webpage(source, client))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            all_docs = []
            for r in results:
                if isinstance(r, list):
                    all_docs.extend(r)
            
            saved = await save_new_documents(all_docs)
            total_saved += saved
            await asyncio.sleep(2)  # Be polite to servers
    
    logger.info(f"Regulatory crawl complete: {total_saved} new documents saved")
    return total_saved
