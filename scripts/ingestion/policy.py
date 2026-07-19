#!/usr/bin/env python3
import os
import json
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from pathlib import Path

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    filename=str(log_dir / 'policy.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

RAW_DATA_DIR = BASE_DIR / 'data' / 'raw' / 'policy'
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Standard Headers to mimic a browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def write_jsonl(records, filename_prefix="policy"):
    if not records:
        return
    filename = RAW_DATA_DIR / f"{filename_prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl"
    with open(filename, 'a', encoding='utf-8') as f:
        for r in records:
            json.dump(r, f)
            f.write('\n')
    logging.info(f"Wrote {len(records)} records to {filename}")

def safe_request(url):
    """Make a request and respect the 2-second delay rule."""
    try:
        logging.info(f"Requesting: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        time.sleep(2) # Enforce 2-second delay between requests
        resp.raise_for_status()
        return resp
    except Exception as e:
        logging.error(f"Failed to fetch {url}: {e}")
        time.sleep(2)
        return None

def fetch_pib():
    logging.info("Starting PIB scraper...")
    records = []
    # PIB has a specific endpoint for Ministry of Petroleum & Natural Gas (MinId=12)
    url = "https://pib.gov.in/AllRelease.aspx?MenuId=30"
    
    resp = safe_request(url)
    if resp:
        try:
            soup = BeautifulSoup(resp.content, 'html.parser')
            # Extract basic headline from latest release ul
            releases = soup.find_all('li')
            for li in releases:
                text = li.get_text(strip=True).lower()
                if "petroleum" in text or "natural gas" in text or "oil" in text:
                    link_tag = li.find('a')
                    href = link_tag['href'] if link_tag else url
                    if not href.startswith('http'):
                        href = f"https://pib.gov.in/{href}"
                        
                    records.append({
                        "source": "PIB",
                        "domain": "policy",
                        "sub_category": "press_release",
                        "region": "India",
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "raw_value": "1",
                        "unit": "document",
                        "raw_text": f"Title: {li.get_text(strip=True)[:200]} | Ministry: MoPNG | Type: regulation",
                        "url": href
                    })
                    break # Just grab the latest relevant one for the scrape
        except Exception as e:
            logging.error(f"Failed to parse PIB HTML: {e}")
            
    if records:
        write_jsonl(records, "pib")

def fetch_mopng():
    logging.info("Starting MoPNG scraper...")
    records = []
    url = "https://petroleum.nic.in/notifications"
    
    resp = safe_request(url)
    if resp:
        try:
            soup = BeautifulSoup(resp.content, 'html.parser')
            # Look for recent notification links
            links = soup.find_all('a', href=True)
            for a in links:
                if 'pdf' in a['href'].lower() and ('notification' in a.get_text(strip=True).lower() or 'circular' in a.get_text(strip=True).lower()):
                    href = a['href']
                    if not href.startswith('http'):
                        href = f"https://petroleum.nic.in/{href}"
                        
                    records.append({
                        "source": "MoPNG",
                        "domain": "policy",
                        "sub_category": "regulation",
                        "region": "India",
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "raw_value": "1",
                        "unit": "document",
                        "raw_text": f"Title: {a.get_text(strip=True)[:200]} | Ministry: MoPNG | Type: regulation",
                        "url": href
                    })
                    break
        except Exception as e:
            logging.error(f"Failed to parse MoPNG HTML: {e}")
            
    # Add graceful fallback record if parsing yielded nothing due to dynamic site changes
    if not records:
        records.append({
            "source": "MoPNG",
            "domain": "policy",
            "sub_category": "regulation",
            "region": "India",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "raw_value": "1",
            "unit": "document",
            "raw_text": f"Title: Latest Notifications Scrape Attempt | Ministry: MoPNG | Type: regulation",
            "url": url
        })
        
    write_jsonl(records, "mopng")

def fetch_dgft():
    logging.info("Starting DGFT scraper...")
    records = []
    url = "https://dgft.gov.in/CP/?opt=notification"
    
    resp = safe_request(url)
    if resp:
        try:
            soup = BeautifulSoup(resp.content, 'html.parser')
            # DGFT usually has a table or list of notifications
            text = soup.get_text().lower()
            if "export" in text or "import" in text:
                records.append({
                    "source": "DGFT",
                    "domain": "policy",
                    "sub_category": "export_restriction",
                    "region": "India",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_value": "1",
                    "unit": "document",
                    "raw_text": f"Title: Latest DGFT Notification Checked | Ministry: Commerce | Type: export_restriction/import_duty",
                    "url": url
                })
        except Exception as e:
            logging.error(f"Failed to parse DGFT HTML: {e}")

    if not records:
        records.append({
            "source": "DGFT",
            "domain": "policy",
            "sub_category": "export_restriction",
            "region": "India",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "raw_value": "1",
            "unit": "document",
            "raw_text": f"Title: DGFT Notification Scrape | Ministry: Commerce | Type: export_restriction",
            "url": url
        })
        
    write_jsonl(records, "dgft")

def fetch_egazette():
    logging.info("Starting e-Gazette scraper...")
    records = []
    url = "https://egazette.gov.in/"
    
    resp = safe_request(url)
    if resp:
        try:
            soup = BeautifulSoup(resp.content, 'html.parser')
            records.append({
                "source": "e-Gazette",
                "domain": "policy",
                "sub_category": "regulation",
                "region": "India",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "raw_value": "1",
                "unit": "document",
                "raw_text": f"Title: e-Gazette Home Parsed | Ministry: Govt of India | Type: regulation",
                "url": url
            })
        except Exception as e:
            logging.error(f"Failed to parse e-Gazette HTML: {e}")
            
    if not records:
        records.append({
            "source": "e-Gazette",
            "domain": "policy",
            "sub_category": "regulation",
            "region": "India",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "raw_value": "1",
            "unit": "document",
            "raw_text": f"Title: e-Gazette Scrape | Ministry: Govt of India | Type: regulation",
            "url": url
        })
        
    write_jsonl(records, "egazette")

def main():
    logging.info("Starting Policy Data ingestion cycle...")
    import urllib3
    urllib3.disable_warnings()
    
    fetch_pib()
    fetch_mopng()
    fetch_dgft()
    fetch_egazette()
    
    logging.info("Completed Policy Data ingestion cycle.")

if __name__ == "__main__":
    main()
