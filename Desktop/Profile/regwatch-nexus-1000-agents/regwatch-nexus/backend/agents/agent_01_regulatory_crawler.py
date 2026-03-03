"""
RegWatch Nexus — Agent 01: Regulatory Crawler
Monitors 160+ regulatory bodies. Runs every 30 minutes.
BACKEND ONLY — never visible to any user.
"""
import feedparser
import requests
import hashlib
import logging
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from supabase_client import supabase_service
from sources.regulatory_sources import REGULATORY_SOURCES

logger = logging.getLogger(__name__)


def crawl_all_regulators():
    """Main entry point called by scheduler every 30 minutes."""
    logger.info(f"[Agent 01] Starting regulatory crawl — {len(REGULATORY_SOURCES)} sources")
    total_new = 0

    for source in REGULATORY_SOURCES:
        try:
            new_docs = crawl_source(source)
            total_new += new_docs
        except Exception as e:
            logger.error(f"[Agent 01] Failed to crawl {source['name']}: {e}")

    logger.info(f"[Agent 01] Crawl complete. {total_new} new documents stored.")
    return total_new


def crawl_source(source: dict) -> int:
    """Crawl a single regulatory source. Returns count of new documents."""
    new_count = 0

    if source.get('feed_url'):
        new_count += crawl_rss(source)
    elif source.get('web_url'):
        new_count += crawl_web(source)

    return new_count


def crawl_rss(source: dict) -> int:
    """Parse RSS/Atom feed and store new documents."""
    new_count = 0
    try:
        feed = feedparser.parse(source['feed_url'])
        for entry in feed.entries[:20]:  # limit to 20 most recent
            url = entry.get('link', '')
            if not url:
                continue

            content_hash = hashlib.sha256(url.encode()).hexdigest()

            # Skip if already processed
            existing = supabase_service.table('source_documents')\
                .select('id').eq('content_hash', content_hash).execute()
            if existing.data:
                continue

            # Store raw document
            doc = {
                'source_type': 'regulator',
                'source_name': source['name'],
                'jurisdiction': source['jurisdiction'],
                'regulator': source['regulator_code'],
                'url': url,
                'title': entry.get('title', ''),
                'raw_content': entry.get('summary', '') or entry.get('description', ''),
                'content_hash': content_hash,
                'published_at': parse_date(entry),
                'processed': False,
            }

            supabase_service.table('source_documents').insert(doc).execute()
            new_count += 1

    except Exception as e:
        logger.error(f"[Agent 01] RSS error for {source['name']}: {e}")

    return new_count


def crawl_web(source: dict) -> int:
    """Scrape web page for new documents."""
    new_count = 0
    try:
        headers = {'User-Agent': 'RegWatch/7.0 Compliance Intelligence (+https://regwatchnexus.com/bot)'}
        response = requests.get(source['web_url'], headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        links = []

        # Extract links matching the source's link selector
        selector = source.get('link_selector', 'a')
        for a in soup.select(selector)[:20]:
            href = a.get('href', '')
            if not href:
                continue
            if href.startswith('/'):
                from urllib.parse import urljoin
                href = urljoin(source['web_url'], href)
            text = a.get_text(strip=True)
            if text and href:
                links.append({'url': href, 'title': text})

        for link in links:
            content_hash = hashlib.sha256(link['url'].encode()).hexdigest()
            existing = supabase_service.table('source_documents')\
                .select('id').eq('content_hash', content_hash).execute()
            if existing.data:
                continue

            doc = {
                'source_type': 'regulator',
                'source_name': source['name'],
                'jurisdiction': source['jurisdiction'],
                'regulator': source['regulator_code'],
                'url': link['url'],
                'title': link['title'],
                'raw_content': link['title'],
                'content_hash': content_hash,
                'published_at': datetime.now(timezone.utc).isoformat(),
                'processed': False,
            }
            supabase_service.table('source_documents').insert(doc).execute()
            new_count += 1

    except Exception as e:
        logger.error(f"[Agent 01] Web crawl error for {source['name']}: {e}")

    return new_count


def parse_date(entry) -> str:
    """Extract and normalise date from feed entry."""
    import time
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        return dt.isoformat()
    return datetime.now(timezone.utc).isoformat()
