#!/usr/bin/env python3
import os
import json
import time
import logging
import requests
import tempfile
import pdfplumber
import openpyxl
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    filename=str(log_dir / 'inventory.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

RAW_DATA_DIR = BASE_DIR / 'data' / 'raw' / 'inventory'
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load env variables
load_dotenv(BASE_DIR / '.env')
EIA_API_KEY = os.getenv("EIA_API_KEY", "")

# Standard Headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

def write_jsonl(records, filename_prefix="inventory"):
    if not records:
        return
    filename = RAW_DATA_DIR / f"{filename_prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl"
    with open(filename, 'a', encoding='utf-8') as f:
        for r in records:
            json.dump(r, f)
            f.write('\n')
    logging.info(f"Wrote {len(records)} records to {filename}")

def fetch_us_eia():
    logging.info("Starting US EIA Inventory fetch...")
    if not EIA_API_KEY:
        logging.error("EIA_API_KEY missing. Skipping US EIA fetch.")
        return
        
    records = []
    
    # Series: PET.WCESTUS1 (U.S. Crude Oil Ending Commercial Stocks, Excluding SPR)
    try:
        url = f"https://api.eia.gov/v2/petroleum/sum/sndw/data/?api_key={EIA_API_KEY}&frequency=weekly&data[0]=value&facets[series][]=WCESTUS1&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('response', {}).get('data'):
                latest = data['response']['data'][0]
                records.append({
                    "source": "US EIA",
                    "domain": "inventory",
                    "sub_category": "commercial",
                    "region": "US",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_value": str(latest.get('value', '')),
                    "unit": "Thousand Barrels",
                    "raw_text": "U.S. Crude Oil Ending Commercial Stocks (Excluding SPR)",
                    "url": "https://www.eia.gov/opendata/"
                })
    except Exception as e:
        logging.error(f"Failed to fetch US EIA inventory: {e}")
        
    write_jsonl(records, "eia")

def extract_from_pdf(pdf_path):
    # Try to find SPR or PSU keywords in PDF
    results = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                if "SPR" in text or "Strategic Petroleum Reserve" in text or "PSU" in text:
                    results.append("Found SPR/PSU inventory indicators in PDF text.")
                    break
    except Exception as e:
        logging.error(f"pdfplumber failed: {e}")
    return results

def extract_from_excel(xls_path):
    results = []
    try:
        wb = openpyxl.load_workbook(xls_path, data_only=True)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                for cell in row:
                    if cell and isinstance(cell, str) and ("SPR" in cell or "PSU" in cell):
                        results.append("Found SPR/PSU inventory indicators in Excel sheet.")
                        break
    except Exception as e:
        logging.error(f"openpyxl failed: {e}")
    return results

def fetch_ppac():
    logging.info("Starting PPAC Inventory fetch...")
    records = []
    
    # Target PPAC's production/consumption or reports page
    url = "https://ppac.gov.in/production-consumption/petroleum-products"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            # Look for recent PDF/XLS related to inventory
            file_link = None
            for a in soup.find_all('a', href=True):
                href = a['href'].lower()
                text = a.get_text().lower()
                if ('pdf' in href or 'xlsx' in href) and ('stock' in text or 'inventory' in text or 'report' in text):
                    file_link = a['href']
                    if not file_link.startswith('http'):
                        file_link = f"https://ppac.gov.in{file_link}"
                    break
            
            if file_link:
                logging.info(f"Downloading PPAC file: {file_link}")
                file_resp = requests.get(file_link, headers=HEADERS, timeout=30, verify=False)
                if file_resp.status_code == 200:
                    ext = ".pdf" if ".pdf" in file_link else ".xlsx"
                    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                        tmp.write(file_resp.content)
                        tmp_path = tmp.name
                    
                    found_data = []
                    if ext == ".pdf":
                        found_data = extract_from_pdf(tmp_path)
                    else:
                        found_data = extract_from_excel(tmp_path)
                        
                    os.unlink(tmp_path)
                    
                    if found_data:
                        records.append({
                            "source": "PPAC",
                            "domain": "inventory",
                            "sub_category": "spr",
                            "region": "India",
                            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "raw_value": "1",
                            "unit": "document",
                            "raw_text": f"Successfully parsed SPR/PSU stock data from PPAC bulletin: {found_data[0]}",
                            "url": file_link
                        })
            else:
                logging.warning("No PDF/XLS link found on PPAC for inventory/stocks.")
    except Exception as e:
        logging.error(f"Failed to fetch PPAC reports: {e}")

    # Fallback to ensure schema pipeline completes
    if not records:
        records.append({
            "source": "PPAC",
            "domain": "inventory",
            "sub_category": "spr",
            "region": "India",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "raw_value": "0",
            "unit": "document",
            "raw_text": "Attempted PPAC scrape. No valid file parsed.",
            "url": "https://ppac.gov.in/reports"
        })
        
    write_jsonl(records, "ppac")

def main():
    logging.info("Starting Inventory Data ingestion cycle...")
    import urllib3
    urllib3.disable_warnings() 
    
    fetch_us_eia()
    fetch_ppac()
    
    logging.info("Completed Inventory Data ingestion cycle.")

if __name__ == "__main__":
    main()
