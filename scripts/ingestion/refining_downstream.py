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
    filename=str(log_dir / 'refining_downstream.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

RAW_DATA_DIR = BASE_DIR / 'data' / 'raw' / 'refining_downstream'
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Load env variables
load_dotenv(BASE_DIR / '.env')
EIA_API_KEY = os.getenv("EIA_API_KEY", "")

# Standard Headers
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
}

def write_jsonl(records, filename_prefix="refining"):
    if not records:
        return
    filename = RAW_DATA_DIR / f"{filename_prefix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl"
    with open(filename, 'a', encoding='utf-8') as f:
        for r in records:
            json.dump(r, f)
            f.write('\n')
    logging.info(f"Wrote {len(records)} records to {filename}")

def safe_request(url):
    try:
        logging.info(f"Requesting: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        time.sleep(2)
        return resp
    except Exception as e:
        logging.error(f"Failed to fetch {url}: {e}")
        time.sleep(2)
        return None

def fetch_us_eia():
    logging.info("Starting US EIA Refining fetch...")
    if not EIA_API_KEY:
        logging.error("EIA_API_KEY missing. Skipping US EIA fetch.")
        return
        
    records = []
    
    # Series: PET.MOPUEUS2.M (U.S. Percent Utilization of Refinery Operable Capacity)
    try:
        url = f"https://api.eia.gov/v2/petroleum/pnp/unc/data/?api_key={EIA_API_KEY}&frequency=monthly&data[0]=value&facets[series][]=MOPUEUS2&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=1"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('response', {}).get('data'):
                latest = data['response']['data'][0]
                records.append({
                    "source": "US EIA",
                    "domain": "refining_downstream",
                    "sub_category": "utilization",
                    "region": "US",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_value": str(latest.get('value', '')),
                    "unit": "Percentage",
                    "raw_text": "U.S. Percent Utilization of Refinery Operable Capacity",
                    "url": "https://www.eia.gov/opendata/"
                })
    except Exception as e:
        logging.error(f"Failed to fetch US EIA refining: {e}")
        
    write_jsonl(records, "eia")

def parse_corporate_pdf(pdf_path, company_name):
    # Search for utilization, capacity, throughput, or crude mix
    found_commentary = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                # Simple heuristic search
                text_lower = text.lower()
                if "utilization" in text_lower or "capacity" in text_lower or "throughput" in text_lower or "crude" in text_lower:
                    # Extract a snippet context
                    snippet = text.replace('\n', ' ')[:500]
                    found_commentary.append(snippet)
                    break # Stop at first good page to avoid huge strings
    except Exception as e:
        logging.error(f"pdfplumber failed on {company_name}: {e}")
    return found_commentary

def fetch_corporate_ir():
    logging.info("Starting Corporate IR scraper...")
    records = []
    
    companies = {
        "IOCL": "https://iocl.com/investor-relations",
        "BPCL": "https://www.bharatpetroleum.in/about-bpcl/investor-relations.aspx",
        "HPCL": "https://www.hindustanpetroleum.com/financial-results",
        "RIL": "https://www.ril.com/investors/financial-reporting"
    }
    
    for company, url in companies.items():
        resp = safe_request(url)
        found_pdf = False
        
        if resp and resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                text = a.get_text().lower()
                
                # Look for financial results or presentation PDFs
                if '.pdf' in href.lower() and ('result' in text or 'presentation' in text or 'quarter' in text or 'q' in text):
                    found_pdf = True
                    if not href.startswith('http'):
                        # Basic resolution, might need domain prepending but we try best effort
                        if href.startswith('/'):
                            # get root domain
                            from urllib.parse import urlparse
                            parsed_uri = urlparse(url)
                            root = '{uri.scheme}://{uri.netloc}'.format(uri=parsed_uri)
                            href = root + href
                    
                    logging.info(f"Downloading {company} PDF: {href}")
                    pdf_resp = safe_request(href)
                    if pdf_resp and pdf_resp.status_code == 200:
                        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                            tmp.write(pdf_resp.content)
                            tmp_path = tmp.name
                            
                        commentary = parse_corporate_pdf(tmp_path, company)
                        os.unlink(tmp_path)
                        
                        if commentary:
                            records.append({
                                "source": company,
                                "domain": "refining_downstream",
                                "sub_category": "throughput",
                                "region": "India",
                                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                                "raw_value": "1",
                                "unit": "document",
                                "raw_text": f"Found IR data for {company}. Snippet: {commentary[0][:200]}...",
                                "url": href
                            })
                    break # One per company
                    
        if not found_pdf:
            logging.warning(f"Could not cleanly find a PDF for {company}, logging a fallback.")
            records.append({
                "source": company,
                "domain": "refining_downstream",
                "sub_category": "throughput",
                "region": "India",
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "raw_value": "0",
                "unit": "document",
                "raw_text": f"Attempted to scrape IR page for {company} but found no easily extractable PDF or was blocked.",
                "url": url
            })

    write_jsonl(records, "corporate_ir")

def extract_from_excel(xls_path):
    results = []
    try:
        wb = openpyxl.load_workbook(xls_path, data_only=True)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                for cell in row:
                    if cell and isinstance(cell, str) and ("throughput" in cell.lower() or "crude processed" in cell.lower()):
                        results.append("Found crude throughput indicators in Excel sheet.")
                        break
    except Exception as e:
        logging.error(f"openpyxl failed: {e}")
    return results

def fetch_ppac():
    logging.info("Starting PPAC Refining fetch...")
    records = []
    
    url = "https://ppac.gov.in/production-consumption/petroleum-products"
    resp = safe_request(url)
    if resp and resp.status_code == 200:
        try:
            soup = BeautifulSoup(resp.content, 'html.parser')
            file_link = None
            for a in soup.find_all('a', href=True):
                href = a['href'].lower()
                text = a.get_text().lower()
                if ('pdf' in href or 'xlsx' in href) and ('throughput' in text or 'refiner' in text or 'production' in text):
                    file_link = a['href']
                    if not file_link.startswith('http'):
                        file_link = f"https://ppac.gov.in{file_link}"
                    break
            
            if file_link:
                logging.info(f"Downloading PPAC file: {file_link}")
                file_resp = requests.get(file_link, headers=HEADERS, timeout=30, verify=False)
                time.sleep(2)
                if file_resp.status_code == 200:
                    ext = ".pdf" if ".pdf" in file_link else ".xlsx"
                    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                        tmp.write(file_resp.content)
                        tmp_path = tmp.name
                    
                    found_data = []
                    if ext == ".pdf":
                        found_data = parse_corporate_pdf(tmp_path, "PPAC")
                    else:
                        found_data = extract_from_excel(tmp_path)
                        
                    os.unlink(tmp_path)
                    
                    if found_data:
                        records.append({
                            "source": "PPAC",
                            "domain": "refining_downstream",
                            "sub_category": "throughput",
                            "region": "India",
                            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "raw_value": "1",
                            "unit": "document",
                            "raw_text": f"Successfully parsed refining throughput from PPAC: {found_data[0][:200]}",
                            "url": file_link
                        })
        except Exception as e:
            logging.error(f"Failed to parse PPAC HTML: {e}")

    if not records:
        records.append({
            "source": "PPAC",
            "domain": "refining_downstream",
            "sub_category": "throughput",
            "region": "India",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "raw_value": "0",
            "unit": "document",
            "raw_text": "Attempted PPAC refining scrape. No valid file parsed.",
            "url": url
        })
        
    write_jsonl(records, "ppac")

def main():
    logging.info("Starting Refining & Downstream Data ingestion cycle...")
    import urllib3
    urllib3.disable_warnings()
    
    fetch_us_eia()
    fetch_corporate_ir()
    fetch_ppac()
    
    logging.info("Completed Refining Data ingestion cycle.")

if __name__ == "__main__":
    main()
