#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
import numpy as np
from rapidfuzz import fuzz
from datetime import datetime, timezone
from pathlib import Path

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(log_dir / 'dedup_quality.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

NORMALIZED_DIR = BASE_DIR / 'data' / 'processed' / 'normalized'
DEDUPED_DIR = BASE_DIR / 'data' / 'processed' / 'deduped'
DEDUPED_DIR.mkdir(parents=True, exist_ok=True)
REPORT_FILE = DEDUPED_DIR / 'quality_report.json'

def compute_hash(row):
    """Compute exact match hash based on source, url, and timestamp."""
    src = str(row.get('source', ''))
    url = str(row.get('url', ''))
    ts = str(row.get('timestamp_utc', ''))
    return hash((src, url, ts))

def fuzzy_dedup_daily_bucket(df_bucket, threshold=90.0):
    """Finds near-duplicates within a single day/domain bucket based on raw_text."""
    if df_bucket.empty or 'raw_text' not in df_bucket.columns:
        return df_bucket
        
    df_bucket = df_bucket.reset_index(drop=True)
    drop_indices = set()
    
    # We do a pairwise comparison. For a single day/domain, N should be small.
    # To be extremely efficient, we only compare rows not already dropped.
    for i in range(len(df_bucket)):
        if i in drop_indices:
            continue
        text_i = str(df_bucket.at[i, 'raw_text']).strip()
        if not text_i or text_i == 'nan':
            continue
            
        for j in range(i + 1, len(df_bucket)):
            if j in drop_indices:
                continue
            text_j = str(df_bucket.at[j, 'raw_text']).strip()
            if not text_j or text_j == 'nan':
                continue
                
            # If length difference is huge, rapidfuzz score won't be > 90 anyway
            if max(len(text_i), len(text_j)) > 0:
                len_ratio = min(len(text_i), len(text_j)) / max(len(text_i), len(text_j))
                if len_ratio < 0.7:
                    continue
                    
            score = fuzz.ratio(text_i, text_j)
            if score >= threshold:
                drop_indices.add(j) # Drop the latter one
                
    if drop_indices:
        return df_bucket.drop(list(drop_indices))
    return df_bucket

def detect_anomalies(df):
    """
    Flag numeric values (raw_value) outside 3 std dev of 30-day trailing mean.
    We group by source, sub_category, and unit.
    """
    if 'raw_value' not in df.columns or 'timestamp_utc' not in df.columns:
        return df, 0
        
    df['numeric_val'] = pd.to_numeric(df['raw_value'], errors='coerce')
    df['date_parsed'] = pd.to_datetime(df['timestamp_utc'], errors='coerce')
    
    df['anomaly_flag'] = False
    mask_valid = df['numeric_val'].notna() & df['date_parsed'].notna()
    if not mask_valid.any():
        df = df.drop(columns=['numeric_val', 'date_parsed'])
        return df, 0
        
    anomalies_found = 0
    group_cols = ['source', 'sub_category', 'unit']
    missing_cols = [c for c in group_cols if c not in df.columns]
    
    if not missing_cols:
        df_valid = df[mask_valid].copy()
        
        for name, group in df_valid.groupby(group_cols):
            if len(group) < 3:
                continue
            group = group.sort_values('date_parsed')
            r = group.rolling('30D', on='date_parsed', min_periods=3)['numeric_val']
            mean = r.mean()
            std = r.std()
            z = (group['numeric_val'] - mean) / std
            flags = (z.abs() > 3).astype(bool)
            # flags.index matches the original df integer index because df_valid was a copy without index reset
            df.loc[flags.index, 'anomaly_flag'] = flags
            
        anomalies_found = int(df['anomaly_flag'].sum())
        
    df = df.drop(columns=['numeric_val', 'date_parsed'], errors='ignore')
    return df, anomalies_found

def process_domain(file_path):
    domain = file_path.name.split('_normalized.jsonl')[0]
    logging.info(f"Processing Dedup & Quality for: {domain}")
    
    try:
        df = pd.read_json(file_path, orient='records', lines=True)
    except Exception as e:
        logging.error(f"Failed reading {file_path}: {e}")
        return None
        
    if df.empty:
        return None
        
    initial_rows = len(df)
    
    # 1. Validation completeness
    required_cols = ['source', 'domain', 'timestamp_utc']
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        logging.warning(f"{domain} is entirely missing required columns {missing_cols}. Dropping all.")
        return {
            "domain": domain,
            "dupes_removed": 0,
            "rows_flagged_incomplete": initial_rows,
            "rows_flagged_anomalous": 0
        }
        
    df_clean = df.dropna(subset=required_cols)
    incomplete_count = initial_rows - len(df_clean)
    
    # 2. Exact Dedup
    df_clean['exact_hash'] = df_clean.apply(compute_hash, axis=1)
    len_before_exact = len(df_clean)
    df_clean = df_clean.drop_duplicates(subset=['exact_hash'], keep='first')
    exact_dupes = len_before_exact - len(df_clean)
    df_clean = df_clean.drop(columns=['exact_hash'])
    
    # 3. Near-Duplicate Fuzzy Dedup (bucketed by date)
    fuzzy_dupes = 0
    if 'timestamp_utc' in df_clean.columns and 'raw_text' in df_clean.columns:
        df_clean['date_bucket'] = df_clean['timestamp_utc'].astype(str).str[:10]
        
        bucketed_dfs = []
        for date_val, group in df_clean.groupby('date_bucket'):
            group_deduped = fuzzy_dedup_daily_bucket(group)
            fuzzy_dupes += len(group) - len(group_deduped)
            bucketed_dfs.append(group_deduped)
            
        if bucketed_dfs:
            df_clean = pd.concat(bucketed_dfs, ignore_index=True)
        df_clean = df_clean.drop(columns=['date_bucket'])

    # 4. Statistical Anomaly Detection
    df_clean, anomalies = detect_anomalies(df_clean)
    
    # Write output
    out_file = DEDUPED_DIR / f"{domain}_deduped.jsonl"
    df_clean.to_json(out_file, orient='records', lines=True)
    
    return {
        "domain": domain,
        "dupes_removed": int(exact_dupes + fuzzy_dupes),
        "rows_flagged_incomplete": int(incomplete_count),
        "rows_flagged_anomalous": int(anomalies)
    }

def main():
    logging.info("Starting Dedup & Quality Pipeline...")
    
    report = {
        "run_time_utc": datetime.now(timezone.utc).isoformat(),
        "domains": {}
    }
    
    total_dupes = 0
    total_incomplete = 0
    total_anomalies = 0
    
    for file_path in NORMALIZED_DIR.glob("*_normalized.jsonl"):
        domain_report = process_domain(file_path)
        if domain_report:
            domain = domain_report.pop('domain')
            report["domains"][domain] = domain_report
            total_dupes += domain_report['dupes_removed']
            total_incomplete += domain_report['rows_flagged_incomplete']
            total_anomalies += domain_report['rows_flagged_anomalous']
            
    report["total_dupes_removed"] = total_dupes
    report["total_rows_flagged_incomplete"] = total_incomplete
    report["total_rows_flagged_anomalous"] = total_anomalies
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=4)
        
    logging.info(f"Dedup & Quality complete. Dupes removed: {total_dupes}, Incomplete dropped: {total_incomplete}, Anomalies flagged: {total_anomalies}.")

if __name__ == "__main__":
    main()
