#!/usr/bin/env python3
import os
import json
import time
import asyncio
import logging
import requests
import websockets
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Setup Logging
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
os.makedirs(log_dir, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(log_dir, 'maritime_logistics.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Setup Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_DATA_DIR = os.path.join(BASE_DIR, 'data', 'raw', 'maritime_logistics')
os.makedirs(RAW_DATA_DIR, exist_ok=True)

# Load environment variables
load_dotenv(os.path.join(BASE_DIR, '.env'))
AISSTREAM_KEY = os.getenv("AISSTREAM_KEY", "")

# Output JSONL helper
def write_jsonl(records, domain='maritime_logistics'):
    filename = os.path.join(RAW_DATA_DIR, f"{domain}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jsonl")
    with open(filename, 'a', encoding='utf-8') as f:
        for r in records:
            json.dump(r, f)
            f.write('\n')
    logging.info(f"Wrote {len(records)} records to {filename}")

# Scraping Functions
def fetch_canal_advisories():
    logging.info("Fetching Canal Advisories...")
    records = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    # Panama Canal
    try:
        url_panama = "https://pancanal.com/en/advisories-to-shipping/"
        resp = requests.get(url_panama, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            # Look for recent advisory links
            # Using a broad net to avoid missing due to layout changes
            links = soup.find_all('a', href=True)
            advisories = [a for a in links if 'advisory' in a.get('href').lower() and a.text.strip()]
            if advisories:
                latest = advisories[0]
                records.append({
                    "source": "Panama Canal Authority",
                    "domain": "maritime_logistics",
                    "sub_category": "canal_advisory",
                    "region": "Panama Canal",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_value": "1",
                    "unit": "advisory",
                    "raw_text": latest.text.strip(),
                    "url": latest.get('href') if latest.get('href').startswith('http') else "https://pancanal.com" + latest.get('href')
                })
    except Exception as e:
        logging.error(f"Failed to fetch Panama Canal advisories: {e}")

    # Suez Canal
    try:
        url_suez = "https://www.suezcanal.gov.eg/English/Navigation/Pages/NavigationCirculars.aspx"
        resp = requests.get(url_suez, headers=headers, timeout=15)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, 'html.parser')
            links = soup.find_all('a', href=True)
            advisories = [a for a in links if 'circular' in a.get('href').lower() and a.text.strip()]
            if advisories:
                latest = advisories[0]
                records.append({
                    "source": "Suez Canal Authority",
                    "domain": "maritime_logistics",
                    "sub_category": "canal_advisory",
                    "region": "Suez Canal",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "raw_value": "1",
                    "unit": "advisory",
                    "raw_text": latest.text.strip(),
                    "url": "https://www.suezcanal.gov.eg" + latest.get('href')
                })
    except Exception as e:
        logging.error(f"Failed to fetch Suez Canal advisories: {e}")

    if records:
        write_jsonl(records, domain='canal_advisories')

# AISstream WebSocket Logic
BOUNDING_BOXES = {
    "Strait of Hormuz": [[24.0, 54.0], [27.0, 57.0]],
    "Bab-el-Mandeb": [[12.0, 43.0], [14.0, 44.5]],
    "Strait of Malacca": [[1.0, 101.0], [6.0, 104.0]]
}

def get_region(lat, lon):
    for region, box in BOUNDING_BOXES.items():
        if box[0][0] <= lat <= box[1][0] and box[0][1] <= lon <= box[1][1]:
            return region
    return "Unknown"

async def consume_ais_stream():
    if not AISSTREAM_KEY:
        logging.error("AISSTREAM_KEY not found in environment. Skipping WebSocket connection.")
        return

    url = "wss://stream.aisstream.io/v0/stream"
    
    # Flatten bounding boxes for subscription
    bounding_boxes_list = [box for box in BOUNDING_BOXES.values()]
    
    subscription = {
        "APIKey": AISSTREAM_KEY,
        "BoundingBoxes": bounding_boxes_list,
        # Filter to PositionReports to get speed and location
        "FiltersShipMMSI": [],
        "FilterMessageTypes": ["PositionReport"]
    }
    
    aggregation_interval = 15 * 60 # 15 minutes
    # State mapping: MMSI -> {speed, region}
    # Reset every interval
    vessel_state = {}
    last_flush_time = time.time()

    logging.info("Connecting to AISstream.io...")
    try:
        async with websockets.connect(url, max_size=None) as websocket:
            await websocket.send(json.dumps(subscription))
            logging.info("Subscribed to AIS stream.")
            
            while True:
                try:
                    message_str = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                    msg = json.loads(message_str)
                    
                    if "Message" in msg and "PositionReport" in msg["Message"]:
                        report = msg["Message"]["PositionReport"]
                        meta = msg.get("MetaData", {})
                        mmsi = report.get("UserID")
                        sog = report.get("Sog") # Speed over ground
                        lat = report.get("Latitude")
                        lon = report.get("Longitude")
                        
                        # We only want Tankers (ShipType 80-89)
                        # We can try to infer from ship type if MetaData includes it, otherwise we take what we have
                        # Note: AISstream PositionReport doesn't always have ShipType, it's in ShipStaticData
                        # However, for simplicity and lacking ShipStaticData stream filtering efficiently here, 
                        # we will log all vessels in the bounding box as a proxy if we can't filter precisely,
                        # OR we filter if MetaData contains ShipType. AISstream MetaData often contains ShipName.
                        # We will just use the vessels reported. In a full production system, we'd join with MMSI registry.
                        
                        if lat and lon and sog is not None:
                            region = get_region(lat, lon)
                            if region != "Unknown":
                                vessel_state[mmsi] = {
                                    "region": region,
                                    "sog": sog
                                }

                    current_time = time.time()
                    if current_time - last_flush_time >= aggregation_interval:
                        # Flush aggregates
                        flush_aggregates(vessel_state)
                        vessel_state = {} # Reset
                        last_flush_time = current_time

                        # Also fetch canal advisories every 15 minutes
                        fetch_canal_advisories()

                except asyncio.TimeoutError:
                    # No messages in 60s, keep waiting
                    current_time = time.time()
                    if current_time - last_flush_time >= aggregation_interval:
                        flush_aggregates(vessel_state)
                        vessel_state = {}
                        last_flush_time = current_time
                        fetch_canal_advisories()

    except Exception as e:
        logging.error(f"WebSocket connection failed: {e}")

def flush_aggregates(vessel_state):
    records = []
    # Group by region
    regions_data = {r: {"count": 0, "speed_sum": 0.0, "stationary": 0} for r in BOUNDING_BOXES.keys()}
    
    for mmsi, data in vessel_state.items():
        r = data["region"]
        sog = data["sog"]
        regions_data[r]["count"] += 1
        regions_data[r]["speed_sum"] += sog
        if sog < 0.5:
            regions_data[r]["stationary"] += 1

    for region, stats in regions_data.items():
        if stats["count"] > 0:
            avg_speed = stats["speed_sum"] / stats["count"]
            records.append({
                "source": "AISstream",
                "domain": "maritime_logistics",
                "sub_category": "chokepoint_congestion",
                "region": region,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "raw_value": str(stats["stationary"]),
                "unit": "stationary_vessels",
                "raw_text": f"vessel_count: {stats['count']}, avg_speed_knots: {avg_speed:.2f}",
                "url": "https://aisstream.io"
            })
            
    if records:
        write_jsonl(records, domain='ais_chokepoints')
        logging.info(f"Flushed AIS aggregates for {len(records)} regions.")
    else:
        logging.info("No vessels tracked in this interval.")

def main():
    logging.info("Starting Maritime Logistics script (Continuous Mode)...")
    # Fetch advisories immediately on startup
    fetch_canal_advisories()
    
    if not AISSTREAM_KEY:
        logging.warning("No AISSTREAM_KEY provided. Only canal advisories were fetched.")
        return
        
    # Run the asyncio loop for WebSocket
    asyncio.run(consume_ais_stream())

if __name__ == "__main__":
    main()
