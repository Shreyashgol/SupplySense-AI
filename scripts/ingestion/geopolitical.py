#!/usr/bin/env python3
import os
import time
import json
import logging
import argparse
import requests
import feedparser
import pandas as pd
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zipfile import ZipFile

# Setup Logging
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(log_dir, 'geopolitical.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Setup Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_DATA_DIR = os.path.join(BASE_DIR, 'data', 'raw', 'geopolitical')
PROCESSED_DATA_DIR = os.path.join(BASE_DIR, 'data', 'processed')
os.makedirs(RAW_DATA_DIR, exist_ok=True)
os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)

# Schema mapping helper
def write_jsonl(records, domain='geopolitical'):
    filename = os.path.join(RAW_DATA_DIR, f"{domain}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl")
    with open(filename, 'a', encoding='utf-8') as f:
        for r in records:
            json.dump(r, f)
            f.write('\n')
    logging.info(f"Wrote {len(records)} records to {filename}")

# Energy-relevant actor countries (ISO3 / FIPS / names depending on source)
ENERGY_ACTORS = ['ARE', 'SAU', 'RUS', 'UKR', 'YEM', 'IND', 'IRN', 'IRQ', 'QAT', 'KWT', 'OMN', 'USA', 'CHN', 'VEN']

def fetch_gdelt():
    logging.info("Starting GDELT fetch...")
    try:
        # Fetch the master file list
        master_url = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
        resp = requests.get(master_url, timeout=10)
        resp.raise_for_status()
        
        lines = resp.text.strip().split('\n')
        # We need the last 24 hours of export files. 24 hours * 4 per hour = 96 files.
        # Format of masterfilelist: <size> <hash> <url>
        export_urls = [line.split(' ')[-1] for line in lines if "export.CSV.zip" in line]
        recent_urls = export_urls[-96:] # Last 24 hours

        gdelt_columns = [
            'GLOBALEVENTID', 'SQLDATE', 'MonthYear', 'Year', 'FractionDate', 'Actor1Code', 'Actor1Name', 'Actor1CountryCode',
            'Actor1KnownGroupCode', 'Actor1EthnicCode', 'Actor1Religion1Code', 'Actor1Religion2Code', 'Actor1Type1Code',
            'Actor1Type2Code', 'Actor1Type3Code', 'Actor2Code', 'Actor2Name', 'Actor2CountryCode', 'Actor2KnownGroupCode',
            'Actor2EthnicCode', 'Actor2Religion1Code', 'Actor2Religion2Code', 'Actor2Type1Code', 'Actor2Type2Code',
            'Actor2Type3Code', 'IsRootEvent', 'EventCode', 'EventBaseCode', 'EventRootCode', 'QuadClass', 'GoldsteinScale',
            'NumMentions', 'NumSources', 'NumArticles', 'AvgTone', 'Actor1Geo_Type', 'Actor1Geo_FullName',
            'Actor1Geo_CountryCode', 'Actor1Geo_ADM1Code', 'Actor1Geo_ADM2Code', 'Actor1Geo_Lat', 'Actor1Geo_Long',
            'Actor1Geo_FeatureID', 'Actor2Geo_Type', 'Actor2Geo_FullName', 'Actor2Geo_CountryCode', 'Actor2Geo_ADM1Code',
            'Actor2Geo_ADM2Code', 'Actor2Geo_Lat', 'Actor2Geo_Long', 'Actor2Geo_FeatureID', 'ActionGeo_Type',
            'ActionGeo_FullName', 'ActionGeo_CountryCode', 'ActionGeo_ADM1Code', 'ActionGeo_ADM2Code', 'ActionGeo_Lat',
            'ActionGeo_Long', 'ActionGeo_FeatureID', 'DATEADDED', 'SOURCEURL'
        ]

        all_records = []
        for url in recent_urls:
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    with ZipFile(BytesIO(r.content)) as z:
                        filename = z.namelist()[0]
                        with z.open(filename) as f:
                            df = pd.read_csv(f, sep='\t', header=None, names=gdelt_columns, dtype=str)
                            
                            # Filter for energy-relevant countries in Actor1CountryCode or Actor2CountryCode
                            # Note: GDELT uses 3-character country codes (FIPS10-4 usually, some are ISO)
                            # We'll use a broad text match on the Name/CountryCode for simplicity and robustness
                            mask = df['Actor1Name'].str.contains('RUSSIA|UKRAINE|SAUDI|UNITED ARAB EMIRATES|YEMEN|INDIA|IRAN|IRAQ|QATAR|KUWAIT|OMAN', case=False, na=False) | \
                                   df['Actor2Name'].str.contains('RUSSIA|UKRAINE|SAUDI|UNITED ARAB EMIRATES|YEMEN|INDIA|IRAN|IRAQ|QATAR|KUWAIT|OMAN', case=False, na=False)
                            
                            df_filtered = df[mask].copy()

                            # Filter for conflict/instability (EventRootCode 14 to 20 are generally coercion, assault, fight, engage in unconventional mass violence)
                            event_codes = ['14', '15', '16', '17', '18', '19', '20']
                            df_filtered = df_filtered[df_filtered['EventRootCode'].isin(event_codes)]

                            for _, row in df_filtered.iterrows():
                                record = {
                                    "source": "GDELT 2.0",
                                    "domain": "geopolitical",
                                    "sub_category": "conflict_event",
                                    "region": row.get('ActionGeo_FullName', ''),
                                    "timestamp_utc": datetime.strptime(str(row['SQLDATE']), "%Y%m%d").isoformat() if pd.notna(row['SQLDATE']) else datetime.now(timezone.utc).isoformat(),
                                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                                    "raw_value": row.get('GoldsteinScale', ''),
                                    "unit": "GoldsteinScale",
                                    "raw_text": f"Event between {row.get('Actor1Name', 'Unknown')} and {row.get('Actor2Name', 'Unknown')}. Type: {row.get('EventCode', '')}",
                                    "url": row.get('SOURCEURL', '')
                                }
                                all_records.append(record)
            except Exception as e:
                logging.warning(f"Failed to process GDELT file {url}: {e}")
                
        if all_records:
            write_jsonl(all_records, domain='gdelt')
        logging.info(f"GDELT fetch complete. Saved {len(all_records)} records.")

    except Exception as e:
        logging.error(f"GDELT fetch failed: {e}")

def fetch_ofac():
    logging.info("Starting OFAC SDN fetch...")
    try:
        url = "https://www.treasury.gov/ofac/downloads/sdn.csv"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        # Read current OFAC list
        df_current = pd.read_csv(BytesIO(resp.content), header=None, dtype=str)
        
        prev_file = os.path.join(PROCESSED_DATA_DIR, 'ofac_previous.csv')
        new_records = []
        
        if os.path.exists(prev_file):
            df_prev = pd.read_csv(prev_file, header=None, dtype=str)
            # Find rows in current that are not in prev. Using the first column (Entity ID)
            current_ids = set(df_current[0].dropna())
            prev_ids = set(df_prev[0].dropna())
            new_ids = current_ids - prev_ids
            
            if new_ids:
                df_new = df_current[df_current[0].isin(new_ids)]
                for _, row in df_new.iterrows():
                    record = {
                        "source": "OFAC SDN",
                        "domain": "geopolitical",
                        "sub_category": "sanctions",
                        "region": "Global",
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "raw_value": "1",
                        "unit": "new_sanction",
                        "raw_text": ", ".join(row.fillna("").values),
                        "url": "https://sanctionslist.ofac.treas.gov"
                    }
                    new_records.append(record)
        else:
            logging.info("No previous OFAC list found. Saving current as baseline.")
            
        # Update baseline
        df_current.to_csv(prev_file, index=False, header=False)
        
        if new_records:
            write_jsonl(new_records, domain='ofac')
            logging.info(f"OFAC fetch complete. Saved {len(new_records)} new records.")
        else:
            logging.info("OFAC fetch complete. No new sanctions.")
            
    except Exception as e:
        logging.error(f"OFAC fetch failed: {e}")

def fetch_rss():
    logging.info("Starting RSS fetch...")
    feeds = [
        ("Crisis Group", "https://www.crisisgroup.org/en/rss.xml"),
        ("BBC World", "http://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml")
    ]
    
    # Set a common user agent
    feedparser.USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    
    all_records = []
    for name, url in feeds:
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:20]: # Latest 20 items
                record = {
                    "source": name,
                    "domain": "geopolitical",
                    "sub_category": "news",
                    "region": "Global",
                    "timestamp_utc": time.strftime('%Y-%m-%dT%H:%M:%SZ', entry.published_parsed) if hasattr(entry, 'published_parsed') and entry.published_parsed else datetime.now(timezone.utc).isoformat(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_value": "1",
                    "unit": "news_article",
                    "raw_text": entry.title + " - " + getattr(entry, 'summary', ''),
                    "url": entry.link
                }
                all_records.append(record)
        except Exception as e:
            logging.error(f"Failed to fetch RSS feed {name} at {url}: {e}")
            
    if all_records:
        write_jsonl(all_records, domain='geopolitical')
    logging.info(f"RSS fetch complete. Saved {len(all_records)} records.")

def main():
    parser = argparse.ArgumentParser(description="Geopolitical Data Ingestion")
    parser.add_argument("--loop", action="store_true", help="Run continuously every 6 hours")
    args = parser.parse_args()

    while True:
        logging.info("Starting geopolitical ingestion cycle...")
        
        fetch_gdelt()
        fetch_ofac()
        fetch_rss()
        
        logging.info("Completed geopolitical ingestion cycle.")
        
        if not args.loop:
            break
            
        logging.info("Sleeping for 6 hours...")
        time.sleep(6 * 3600)

if __name__ == "__main__":
    main()
