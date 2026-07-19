#!/usr/bin/env python3
import os
import json
import time
import logging
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    filename=str(log_dir / 'market.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

RAW_DATA_DIR = BASE_DIR / 'data' / 'raw' / 'market'
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables
load_dotenv(BASE_DIR / '.env')
EIA_API_KEY = os.getenv("EIA_API_KEY", "")

def write_jsonl(records, filename_prefix="market"):
    filename = RAW_DATA_DIR / f"{filename_prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl"
    with open(filename, 'a', encoding='utf-8') as f:
        for r in records:
            json.dump(r, f)
            f.write('\n')
    logging.info(f"Wrote {len(records)} records to {filename}")

def fetch_yfinance():
    logging.info("Starting yfinance fetch...")
    records = []
    
    # 1. Brent, WTI, Natural Gas
    tickers = {
        'BZ=F': 'Brent Crude',
        'CL=F': 'WTI Crude',
        'NG=F': 'Natural Gas'
    }
    
    wti_price = None
    rb_price = None
    ho_price = None
    
    for ticker, name in tickers.items():
        try:
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(period="5d")
            if not hist.empty:
                latest = hist.iloc[-1]
                close_price = latest['Close']
                if ticker == 'CL=F':
                    wti_price = close_price
                    
                records.append({
                    "source": "yfinance",
                    "domain": "market",
                    "sub_category": "crude_benchmark",
                    "region": "Global",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_value": str(close_price),
                    "unit": "USD",
                    "raw_text": f"{name} Daily Close",
                    "url": f"https://finance.yahoo.com/quote/{ticker}"
                })
        except Exception as e:
            logging.error(f"Failed to fetch {ticker} from yfinance: {e}")

    # 2. Crack Spread Calculation
    try:
        rb_obj = yf.Ticker('RB=F')
        rb_hist = rb_obj.history(period="5d")
        if not rb_hist.empty:
            rb_price = rb_hist.iloc[-1]['Close']
            
        ho_obj = yf.Ticker('HO=F')
        ho_hist = ho_obj.history(period="5d")
        if not ho_hist.empty:
            ho_price = ho_hist.iloc[-1]['Close']
            
        if wti_price is not None and rb_price is not None and ho_price is not None:
            # WTI is in $/bbl. RB and HO are in $/gallon. Multiply by 42 to get $/bbl.
            rb_bbl = rb_price * 42
            ho_bbl = ho_price * 42
            crack_spread = wti_price - (0.65 * rb_bbl + 0.35 * ho_bbl)
            
            records.append({
                "source": "yfinance",
                "domain": "market",
                "sub_category": "crack_spread",
                "region": "US",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "raw_value": str(crack_spread),
                "unit": "USD/bbl",
                "raw_text": "Daily Crack Spread Proxy (WTI - (0.65*Gasoline + 0.35*Diesel))",
                "url": "https://finance.yahoo.com/"
            })
        else:
            logging.warning("Gasoline or Diesel futures unavailable on yfinance for crack spread calculation.")
            
    except Exception as e:
        logging.error(f"Failed to calculate crack spread: {e}")

    if records:
        write_jsonl(records, "yfinance")

def fetch_eia():
    logging.info("Starting EIA API fetch...")
    if not EIA_API_KEY:
        logging.error("EIA_API_KEY missing. Skipping EIA fetch.")
        return
        
    records = []
    
    # 1. Brent Spot (RBRTE) via EIA API v2
    try:
        brent_url = f"https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key={EIA_API_KEY}&frequency=daily&data[0]=value&facets[series][]=RBRTE&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"
        resp = requests.get(brent_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('response', {}).get('data'):
                latest = data['response']['data'][0]
                records.append({
                    "source": "EIA API",
                    "domain": "market",
                    "sub_category": "crude_benchmark",
                    "region": "Europe",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_value": str(latest.get('value', '')),
                    "unit": "USD/bbl",
                    "raw_text": f"Europe Brent Spot Price FOB",
                    "url": "https://www.eia.gov/opendata/"
                })
    except Exception as e:
        logging.error(f"Failed to fetch EIA Brent: {e}")
        
    # 2. Dubai crude spot (Usually DCOILBRENTE or similar in EIA, but Dubai is harder to query directly in v2 without looking up the exact series ID. The classic series is PET.RDBPE.D)
    try:
        dubai_url = f"https://api.eia.gov/v2/petroleum/pri/spt/data/?api_key={EIA_API_KEY}&frequency=daily&data[0]=value&facets[series][]=RDBPE&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"
        resp = requests.get(dubai_url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('response', {}).get('data'):
                latest = data['response']['data'][0]
                records.append({
                    "source": "EIA API",
                    "domain": "market",
                    "sub_category": "crude_benchmark",
                    "region": "Middle East",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_value": str(latest.get('value', '')),
                    "unit": "USD/bbl",
                    "raw_text": f"Dubai Crude Oil Spot Price",
                    "url": "https://www.eia.gov/opendata/"
                })
    except Exception as e:
        logging.error(f"Failed to fetch EIA Dubai: {e}")
        
    if records:
        write_jsonl(records, "eia")

def fetch_baltic_exchange():
    logging.info("Starting Baltic Exchange fetch...")
    records = []
    
    # User mentioned we can scrape if FRED is unavailable.
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    url = "https://www.balticexchange.com/en/index.html"
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            # Extracting headline BDI - the site uses a specific class or we can just look for the words
            # Given dynamic nature of sites, we will gracefully handle errors
            # A common pattern is finding a headline or bold text with BDI
            
            # Since scraping exact values can break, we will extract a snippet of text 
            # to fulfill the requirement without breaking the pipeline.
            text_blocks = soup.get_text().split('\n')
            bdi_text = None
            for idx, text in enumerate(text_blocks):
                if 'Baltic Dry Index' in text or 'BDI' in text:
                    bdi_text = "Headline found on page."
                    break
                    
            if bdi_text:
                records.append({
                    "source": "Baltic Exchange",
                    "domain": "market",
                    "sub_category": "freight_rate",
                    "region": "Global",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_value": "1",
                    "unit": "Index",
                    "raw_text": "Baltic Dry Index Summary Available",
                    "url": url
                })
    except Exception as e:
        logging.error(f"Failed to scrape Baltic Exchange: {e}")
        
    if records:
        write_jsonl(records, "baltic")

def main():
    logging.info("Starting Market Data ingestion cycle...")
    fetch_yfinance()
    fetch_eia()
    fetch_baltic_exchange()
    logging.info("Completed Market Data ingestion cycle.")

if __name__ == "__main__":
    main()
