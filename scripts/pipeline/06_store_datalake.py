#!/usr/bin/env python3
import os
import sys
import glob
import logging
import duckdb
from pathlib import Path

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(log_dir / 'datalake_load.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

RAW_DIR = BASE_DIR / 'data' / 'raw'
RESOLVED_DIR = BASE_DIR / 'data' / 'processed' / 'entity_resolved'

DATALAKE_DIR = BASE_DIR / 'data' / 'datalake'
DATALAKE_RAW_DIR = DATALAKE_DIR / 'raw'
DATALAKE_PROCESSED_DIR = DATALAKE_DIR / 'processed'
DB_FILE = DATALAKE_DIR / 'energy_resilience.duckdb'

DATALAKE_DIR.mkdir(parents=True, exist_ok=True)
DATALAKE_RAW_DIR.mkdir(parents=True, exist_ok=True)
DATALAKE_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

def initialize_db():
    conn = duckdb.connect(str(DB_FILE))
    # Enable spatial and json extensions if needed
    # conn.execute("INSTALL json; LOAD json;")
    return conn

def load_and_export_raw(conn):
    logging.info("Loading RAW data into Data Lake...")
    # Get all .jsonl files in data/raw/**/*.jsonl
    raw_files = []
    # Using Path.rglob
    for p in RAW_DIR.rglob("*.jsonl"):
        raw_files.append(str(p))
        
    if not raw_files:
        logging.warning("No raw JSONL files found.")
        return 0

    # We use read_json_auto with union_by_name to handle different schemas across domains
    query_create = f"""
    CREATE OR REPLACE TABLE raw_events AS 
    SELECT *,
           domain AS partition_domain,
           SUBSTRING(CAST(timestamp_utc AS VARCHAR), 1, 10) AS partition_date
    FROM read_json_auto({raw_files}, union_by_name=True)
    """
    conn.execute(query_create)
    
    count = conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0]
    logging.info(f"Loaded {count} rows into raw_events table.")
    
    # Export to Partitioned Parquet
    # We clear the existing parquet dir to prevent duplicates on rerun
    export_query = f"""
    COPY raw_events TO '{str(DATALAKE_RAW_DIR)}' 
    (FORMAT PARQUET, PARTITION_BY (partition_domain, partition_date), OVERWRITE_OR_IGNORE 1)
    """
    conn.execute(export_query)
    logging.info("Exported raw_events to Partitioned Parquet.")
    return count

def load_and_export_processed(conn):
    logging.info("Loading PROCESSED data into Data Lake...")
    processed_files = []
    for p in RESOLVED_DIR.rglob("*.jsonl"):
        processed_files.append(str(p))
        
    if not processed_files:
        logging.warning("No processed JSONL files found.")
        return 0

    query_create = f"""
    CREATE OR REPLACE TABLE processed_events AS 
    SELECT *,
           domain AS partition_domain,
           SUBSTRING(CAST(timestamp_utc AS VARCHAR), 1, 10) AS partition_date
    FROM read_json_auto({processed_files}, union_by_name=True)
    """
    conn.execute(query_create)
    
    count = conn.execute("SELECT COUNT(*) FROM processed_events").fetchone()[0]
    logging.info(f"Loaded {count} rows into processed_events table.")
    
    export_query = f"""
    COPY processed_events TO '{str(DATALAKE_PROCESSED_DIR)}' 
    (FORMAT PARQUET, PARTITION_BY (partition_domain, partition_date), OVERWRITE_OR_IGNORE 1)
    """
    conn.execute(export_query)
    logging.info("Exported processed_events to Partitioned Parquet.")
    return count

def create_views(conn):
    logging.info("Creating SQL Views...")
    
    # 1. Daily Domain Counts
    conn.execute("""
    CREATE OR REPLACE VIEW v_daily_domain_counts AS
    SELECT 
        partition_date AS event_date,
        domain,
        COUNT(*) as event_count
    FROM processed_events
    GROUP BY partition_date, domain
    ORDER BY event_date DESC, event_count DESC
    """)
    
    # 2. High Urgency Events
    # Notice we check if urgency_score column exists dynamically in SQL using TRY_CAST or coalesce if it might be missing
    # In duckdb, union_by_name handles missing columns with NULL.
    conn.execute("""
    CREATE OR REPLACE VIEW v_high_urgency_events AS
    SELECT 
        timestamp_utc,
        domain,
        source,
        urgency_score,
        event_category,
        resolved_entities,
        raw_text,
        url
    FROM processed_events
    WHERE urgency_score > 0.5
    ORDER BY urgency_score DESC, timestamp_utc DESC
    """)
    
    # 3. Chokepoint Activity
    # geo_tags is a list of structs. We can filter events where any geo_tag type is 'chokepoint'
    # Wait, duckdb handles JSON arrays. Let's do a simple string match on the raw geo_tags string or use list extensions.
    # Since duckdb infers schema, geo_tags is a LIST(STRUCT(...)).
    # We can unnest it or cast to string and use LIKE. Casting to string is safer if schema varies.
    conn.execute("""
    CREATE OR REPLACE VIEW v_chokepoint_activity AS
    SELECT 
        timestamp_utc,
        domain,
        linked_event_id,
        event_category,
        resolved_entities,
        geo_tags
    FROM processed_events
    WHERE CAST(geo_tags AS VARCHAR) LIKE '%chokepoint%'
    ORDER BY timestamp_utc DESC
    """)
    
    logging.info("Created views: v_daily_domain_counts, v_high_urgency_events, v_chokepoint_activity")

def main():
    logging.info("Starting Data Lake Load Process...")
    conn = initialize_db()
    
    try:
        raw_count = load_and_export_raw(conn)
        processed_count = load_and_export_processed(conn)
        
        if processed_count > 0:
            create_views(conn)
            
        logging.info(f"Data Lake update complete. Raw events: {raw_count}, Processed events: {processed_count}.")
    except Exception as e:
        logging.error(f"Error updating Data Lake: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
