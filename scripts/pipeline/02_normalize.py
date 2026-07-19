#!/usr/bin/env python3
import os
import sys
import json
import yaml
import logging
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from dateutil import parser as dt_parser

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(log_dir / 'normalize.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

RAW_DIR = BASE_DIR / 'data' / 'raw'
PROCESSED_DIR = BASE_DIR / 'data' / 'processed' / 'normalized'
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
ALIASES_YAML = BASE_DIR / 'config' / 'entity_aliases.yaml'
REPORT_FILE = PROCESSED_DIR / 'normalization_report.json'

def load_aliases():
    if not ALIASES_YAML.exists():
        logging.warning("Aliases config not found, skipping entity resolution.")
        return {}
    with open(ALIASES_YAML, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # Flatten to {alias: canonical}
    alias_map = {}
    for category, entities in config.items():
        for canonical, aliases in entities.items():
            # Identity map
            alias_map[canonical.lower()] = canonical
            for a in aliases:
                alias_map[a.lower()] = canonical
    return alias_map

def load_fx_rates():
    """Extract USD-based FX rates from the financial domain raw files."""
    fx_rates = {} # format: { currency_code: { date_str: rate } }
    fx_rates['USD'] = {'latest': 1.0}
    
    financial_dir = RAW_DIR / 'financial'
    if not financial_dir.exists():
        return fx_rates
        
    for file_path in financial_dir.glob("currencies_*.jsonl"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip(): continue
                    row = json.loads(line)
                    # Expected format: raw_value is rate, unit is USD/INR etc.
                    unit = row.get('unit', '')
                    if 'USD/' in unit:
                        target_curr = unit.split('/')[1]
                        val = float(row.get('raw_value', 1.0))
                        date = row.get('timestamp_utc', '').split('T')[0]
                        if target_curr not in fx_rates:
                            fx_rates[target_curr] = {}
                        fx_rates[target_curr][date] = val
                        fx_rates[target_curr]['latest'] = val # Cache latest
        except Exception as e:
            logging.error(f"Failed parsing FX from {file_path}: {e}")
            
    return fx_rates

def convert_to_usd(value, unit, date_str, fx_rates):
    """Converts a value to USD if unit indicates foreign currency."""
    if pd.isna(value) or value == "":
        return value, unit
        
    # Check for known currencies
    for curr in fx_rates.keys():
        if curr != 'USD' and curr in str(unit).upper():
            try:
                v = float(value)
                # Attempt to get same-day rate, else fallback to 'latest'
                rate = fx_rates[curr].get(date_str, fx_rates[curr].get('latest', None))
                if rate:
                    return str(v / rate), 'USD' # e.g., INR to USD requires dividing by USD/INR rate
            except ValueError:
                pass
    return value, unit

def standardize_units(value, unit):
    """Converts volume/distance metrics."""
    if pd.isna(value) or value == "":
        return value, unit
        
    u_lower = str(unit).lower()
    try:
        v = float(value)
        if "liter" in u_lower or "litre" in u_lower:
            return str(v / 158.987), "barrels"
        elif "tmt" in u_lower:
            # TMT to barrels roughly: 1 metric tonne of crude ~ 7.33 barrels
            # 1 TMT = 1000 Tonnes = 7330 barrels
            return str(v * 7330), "barrels"
    except ValueError:
        pass
    
    return value, unit

def parse_iso_utc(ts):
    if pd.isna(ts) or ts == "":
        return None
    try:
        dt = dt_parser.parse(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ts

def normalize_domain(domain_dir, alias_map, fx_rates):
    domain = domain_dir.name
    logging.info(f"Normalizing domain: {domain}")
    
    all_rows = []
    for file_path in domain_dir.glob("*.jsonl"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        all_rows.append(json.loads(line))
        except Exception as e:
            logging.error(f"Error reading {file_path}: {e}")
            
    if not all_rows:
        return 0, 0
        
    df = pd.DataFrame(all_rows)
    initial_count = len(df)
    ambiguous_count = 0
    
    # 1. Timestamps to UTC ISO-8601
    if 'timestamp_utc' in df.columns:
        df['timestamp_utc'] = df['timestamp_utc'].apply(parse_iso_utc)
    if 'retrieved_at' in df.columns:
        df['retrieved_at'] = df['retrieved_at'].apply(parse_iso_utc)
        
    # 2. Currency & 3. Units
    if 'raw_value' in df.columns and 'unit' in df.columns and 'timestamp_utc' in df.columns:
        for idx, row in df.iterrows():
            val = row['raw_value']
            unit = row['unit']
            date_str = str(row['timestamp_utc']).split('T')[0] if pd.notna(row['timestamp_utc']) else ""
            
            # FX
            val, unit = convert_to_usd(val, unit, date_str, fx_rates)
            # Units
            val, unit = standardize_units(val, unit)
            
            df.at[idx, 'raw_value'] = val
            df.at[idx, 'unit'] = unit

    # 4. Entity Resolution (Canonical forms)
    def resolve_text(text):
        if pd.isna(text) or not isinstance(text, str):
            return text
        # Simple word boundary replace (could be optimized with regex for exact words)
        import re
        res = text
        # Sort by length descending to match longest phrases first
        for alias in sorted(alias_map.keys(), key=len, reverse=True):
            canonical = alias_map[alias]
            # Word boundary regex, case insensitive
            pattern = re.compile(r'\b' + re.escape(alias) + r'\b', re.IGNORECASE)
            res = pattern.sub(canonical, res)
        return res

    if 'region' in df.columns:
        df['region'] = df['region'].apply(resolve_text)
    if 'raw_text' in df.columns:
        df['raw_text'] = df['raw_text'].apply(resolve_text)
        
    # Check for ambiguity (mock heuristic: if raw_text contains 'unknown' or value is null)
    if 'raw_value' in df.columns:
        ambiguous_count = df['raw_value'].isna().sum()

    # Write output
    out_file = PROCESSED_DIR / f"{domain}_normalized.jsonl"
    df.to_json(out_file, orient='records', lines=True)
    
    return initial_count, ambiguous_count

def main():
    logging.info("Starting Normalization Pipeline...")
    alias_map = load_aliases()
    fx_rates = load_fx_rates()
    
    report = {
        "run_time_utc": datetime.now(timezone.utc).isoformat(),
        "domains": {}
    }
    
    total_processed = 0
    total_ambiguous = 0
    
    for domain_dir in RAW_DIR.iterdir():
        if not domain_dir.is_dir() or domain_dir.name.startswith('_'):
            continue
            
        rows, ambig = normalize_domain(domain_dir, alias_map, fx_rates)
        report["domains"][domain_dir.name] = {
            "rows_normalized": int(rows),
            "rows_flagged_ambiguous": int(ambig)
        }
        total_processed += int(rows)
        total_ambiguous += int(ambig)
        
    report["total_rows_normalized"] = int(total_processed)
    report["total_rows_flagged_ambiguous"] = int(total_ambiguous)
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=4)
        
    logging.info(f"Normalization complete. Processed {total_processed} rows. Report written to {REPORT_FILE}")

if __name__ == "__main__":
    main()
