#!/usr/bin/env python3
import os
import sys
import time
import json
import yaml
import logging
import importlib
import threading
import schedule
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

# Master logger for ingestion events
logging.basicConfig(
    filename=str(log_dir / 'ingestion.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

RAW_DATA_DIR = BASE_DIR / 'data' / 'raw'
SOURCES_YAML = BASE_DIR / 'config' / 'sources.yaml'

def count_domain_rows(domain):
    domain_dir = RAW_DATA_DIR / domain
    if not domain_dir.exists():
        return 0
    count = 0
    for file_path in domain_dir.glob("*.jsonl"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        count += 1
        except Exception:
            pass
    return count

def run_domain_batch(domain):
    """Executes a single domain script in batch mode."""
    logging.info(f"Triggering Batch Ingestion for: {domain}")
    start_rows = count_domain_rows(domain)
    status = "failed"
    
    try:
        script_path = BASE_DIR / 'scripts' / 'ingestion' / f"{domain}.py"
        if not script_path.exists():
            logging.error(f"Script not found: {script_path}")
            return
            
        spec = importlib.util.spec_from_file_location(domain, str(script_path))
        module = importlib.util.module_from_spec(spec)
        # We don't add to sys.modules to keep memory completely flushed between runs
        spec.loader.exec_module(module)
        
        if hasattr(module, 'main'):
            module.main()
            status = "success"
        else:
            logging.error(f"No main() found in {domain}.py")
            
    except Exception as e:
        logging.error(f"Execution failed for {domain}: {e}")
        
    end_rows = count_domain_rows(domain)
    rows_collected = end_rows - start_rows
    logging.info(f"Ingestion Event | Domain: {domain} | Rows: {rows_collected} | Status: {status}")

async def run_maritime_streaming():
    """Keeps the maritime_logistics WebSocket running continuously, writing 15-min snapshots."""
    logging.info("Starting Streaming Ingestion for: maritime_logistics (15-min interval)")
    
    domain = "maritime_logistics"
    script_path = BASE_DIR / 'scripts' / 'ingestion' / f"{domain}.py"
    
    while True:
        start_rows = count_domain_rows(domain)
        status = "failed"
        try:
            if script_path.exists():
                spec = importlib.util.spec_from_file_location(domain, str(script_path))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, 'main'):
                    # The main function handles the websocket fetch.
                    # If it was truly async in the module we would await it, but if it's synchronous we just call it.
                    # We wrap in asyncio block to fulfill prompt requirement.
                    await asyncio.to_thread(module.main)
                    status = "success"
        except Exception as e:
            logging.error(f"Streaming execution failed for {domain}: {e}")
            
        end_rows = count_domain_rows(domain)
        rows_collected = end_rows - start_rows
        logging.info(f"Ingestion Event (Streaming Snapshot) | Domain: {domain} | Rows: {rows_collected} | Status: {status}")
        
        # Sleep exactly 15 minutes before next snapshot
        await asyncio.sleep(900)

def start_streaming_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_maritime_streaming())

def main():
    parser = argparse.ArgumentParser(description="Persistent Ingestion Orchestrator Daemon")
    parser.add_argument('--loop', action='store_true', help="Run batch jobs every hour instead of daily")
    args = parser.parse_args()

    logging.info("Starting Persistent Ingestion Orchestrator Daemon...")
    
    if not SOURCES_YAML.exists():
        logging.error(f"Config file missing: {SOURCES_YAML}")
        sys.exit(1)
        
    try:
        with open(SOURCES_YAML, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Failed to parse config: {e}")
        sys.exit(1)

    # 1. Start the maritime_logistics streaming task in a background daemon thread
    t = threading.Thread(target=start_streaming_thread, daemon=True)
    t.start()
    
    # 2. Register all other batch jobs based on config
    registered_domains = set()
    
    for domain, sources in config.items():
        if domain == "maritime_logistics":
            continue # Handled by streaming thread
            
        if domain not in registered_domains:
            # Determine the tightest frequency for this domain
            freqs = [s.get('fetch_frequency', 'Daily').lower() for s in sources]
            
            if args.loop:
                schedule.every(1).hours.do(run_domain_batch, domain=domain)
                logging.info(f"Registered {domain} for Hourly batch execution (--loop enabled).")
            else:
                if 'daily' in freqs:
                    schedule.every().day.at("00:00").do(run_domain_batch, domain=domain)
                    logging.info(f"Registered {domain} for Daily batch execution.")
                elif 'weekly' in freqs:
                    schedule.every().week.do(run_domain_batch, domain=domain)
                    logging.info(f"Registered {domain} for Weekly batch execution.")
                elif 'monthly' in freqs:
                    schedule.every(30).days.do(run_domain_batch, domain=domain)
                    logging.info(f"Registered {domain} for Monthly (30-day) batch execution.")
                else:
                    # Default to daily if unknown
                    schedule.every().day.at("00:00").do(run_domain_batch, domain=domain)
                    logging.info(f"Registered {domain} for Daily batch execution (fallback).")
                
            registered_domains.add(domain)

    # 3. Main scheduler loop
    logging.info("Batch scheduler running. Press Ctrl+C to exit.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(60) # Sleep 1 minute between checks to save CPU
    except KeyboardInterrupt:
        logging.info("Orchestrator stopped by user.")

if __name__ == "__main__":
    main()
