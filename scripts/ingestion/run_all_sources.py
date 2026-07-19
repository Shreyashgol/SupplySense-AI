#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import argparse
import importlib
from datetime import datetime, timezone
from pathlib import Path
import re

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    filename=str(log_dir / 'ingestion_master.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Also log to console for the master script
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

RAW_DATA_DIR = BASE_DIR / 'data' / 'raw'
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_FILE = RAW_DATA_DIR / '_ingestion_run_summary.json'
SOURCES_YAML = BASE_DIR / 'config' / 'sources.yaml'

ALL_DOMAINS = [
    'geopolitical',
    'maritime_logistics',
    'market',
    'financial',
    'weather_climate',
    'policy',
    'inventory',
    'refining_downstream',
    'historical'
]

def count_domain_rows(domain):
    """Count the total number of valid lines in all .jsonl files for a given domain."""
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

def update_yaml_last_run(domain, timestamp_iso):
    """Safely update the sources.yaml file using regex to preserve comments."""
    if not SOURCES_YAML.exists():
        return
        
    try:
        with open(SOURCES_YAML, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # We look for the domain block. For example: `domain: "market"`
        # and we want to insert `last_successful_run: "..."` below it if not exists,
        # or replace it if it does.
        
        # Regex to find domain lines and either update an existing last_successful_run or append it
        domain_pattern = f'(    domain: "{domain}"\\n)'
        
        def replace_func(match):
            return f'{match.group(1)}    last_successful_run: "{timestamp_iso}"\n'
            
        # Strip old timestamps for this domain so we don't duplicate them
        old_ts_pattern = f'(    domain: "{domain}"\\n)(?:    last_successful_run: ".*?"\\n)+'
        content = re.sub(old_ts_pattern, r'\1', content)
        
        # Now insert the new one right below the domain declaration
        new_content = re.sub(domain_pattern, replace_func, content)
        
        with open(SOURCES_YAML, 'w', encoding='utf-8') as f:
            f.write(new_content)
    except Exception as e:
        logging.error(f"Failed to update sources.yaml for {domain}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Master Ingestion Orchestrator")
    parser.add_argument('--domains', type=str, help="Comma-separated list of domains to run (e.g. market,financial)")
    args = parser.parse_args()
    
    if args.domains:
        domains_to_run = [d.strip() for d in args.domains.split(',')]
        # Validate domains
        invalid = [d for d in domains_to_run if d not in ALL_DOMAINS]
        if invalid:
            logging.error(f"Invalid domains provided: {invalid}. Allowed: {ALL_DOMAINS}")
            sys.exit(1)
    else:
        domains_to_run = ALL_DOMAINS

    logging.info(f"Starting master ingestion run for domains: {domains_to_run}")
    
    run_summary = {
        "run_start_utc": datetime.now(timezone.utc).isoformat(),
        "domains": {}
    }
    
    total_start_time = time.time()
    
    for domain in domains_to_run:
        logging.info(f"--- Triggering domain: {domain} ---")
        start_time = time.time()
        start_rows = count_domain_rows(domain)
        status = "failed"
        
        try:
            # Dynamically import the domain script
            module_name = domain
            # We need to add scripts/ingestion to sys.path if not there, or import dynamically from file
            script_path = BASE_DIR / 'scripts' / 'ingestion' / f"{domain}.py"
            
            if not script_path.exists():
                logging.error(f"Script not found: {script_path}")
                continue
                
            spec = importlib.util.spec_from_file_location(module_name, str(script_path))
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # Execute main
            if hasattr(module, 'main'):
                module.main()
                status = "success"
                # Update YAML on success
                update_yaml_last_run(domain, datetime.now(timezone.utc).isoformat())
            else:
                logging.error(f"No main() function found in {domain}.py")
                
        except Exception as e:
            logging.error(f"Execution failed for {domain}: {e}")
            status = "failed"
            
        end_time = time.time()
        end_rows = count_domain_rows(domain)
        rows_collected = end_rows - start_rows
        duration = round(end_time - start_time, 2)
        
        logging.info(f"Finished {domain}: Status={status}, Rows Collected={rows_collected}, Duration={duration}s")
        
        run_summary["domains"][domain] = {
            "status": status,
            "rows_collected": rows_collected,
            "duration_seconds": duration,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }

    run_summary["run_end_utc"] = datetime.now(timezone.utc).isoformat()
    run_summary["total_duration_seconds"] = round(time.time() - total_start_time, 2)
    
    try:
        with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(run_summary, f, indent=4)
        logging.info(f"Run summary written to {SUMMARY_FILE}")
    except Exception as e:
        logging.error(f"Failed to write run summary: {e}")

if __name__ == "__main__":
    main()
