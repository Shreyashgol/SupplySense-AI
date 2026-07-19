#!/usr/bin/env python3
import os
import sys
import time
import json
import logging
import subprocess
from pathlib import Path

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(log_dir / 'pipeline_master.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(message)s'))
logging.getLogger().addHandler(console_handler)

def check_directory_has_files(directory, glob_pattern="*.jsonl"):
    path = Path(directory)
    if not path.exists():
        return False
    return any(path.rglob(glob_pattern))

def count_lines_in_dir(directory, glob_pattern="*.jsonl"):
    total = 0
    path = Path(directory)
    if not path.exists():
        return total
    for p in path.rglob(glob_pattern):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                total += sum(1 for line in f if line.strip())
        except Exception:
            pass
    return total

def run_script(script_path):
    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            check=True,
            capture_output=True,
            text=True
        )
        duration = time.time() - start
        return True, duration, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        duration = time.time() - start
        return False, duration, e.stdout, e.stderr

def main():
    logging.info("=========================================")
    logging.info("Starting Master Pipeline Runner (Part B)")
    logging.info("=========================================\n")
    
    # 1. Pre-flight Check
    raw_dir = BASE_DIR / 'data' / 'raw'
    if not check_directory_has_files(raw_dir):
        logging.error("❌ ERROR: The data/raw/ directory is empty!")
        logging.error("   It appears Part A (Data Ingestion) has not been run yet.")
        logging.error("   Please run `python3 scripts/ingestion/run_all_sources.py` first.")
        sys.exit(1)
        
    scripts = [
        ("Normalization", "02_normalize.py", BASE_DIR / 'data' / 'processed' / 'normalized'),
        ("Dedup & Quality", "03_dedup_quality.py", BASE_DIR / 'data' / 'processed' / 'deduped'),
        ("NLP Enrichment", "04_nlp_extraction.py", BASE_DIR / 'data' / 'processed' / 'nlp_enriched'),
        ("Entity Resolution", "05_entity_resolution.py", BASE_DIR / 'data' / 'processed' / 'entity_resolved'),
        ("Data Lake Storage", "06_store_datalake.py", BASE_DIR / 'data' / 'datalake' / 'processed') # Parquet output
    ]
    
    results = []
    
    # Initial input count
    current_input_count = count_lines_in_dir(raw_dir)
    
    for stage_name, script_name, out_dir in scripts:
        script_path = BASE_DIR / 'scripts' / 'pipeline' / script_name
        logging.info(f"⏳ Running {stage_name} ({script_name})...")
        
        success, duration, stdout, stderr = run_script(script_path)
        
        if not success:
            logging.error(f"❌ {stage_name} FAILED!")
            logging.error(f"Error output:\n{stderr}")
            sys.exit(1)
            
        # For data lake, it outputs parquet, so we count records via duckdb if we want, or just rely on the previous stage's count
        if script_name == "06_store_datalake.py":
            try:
                import duckdb
                conn = duckdb.connect(str(BASE_DIR / 'data' / 'datalake' / 'energy_resilience.duckdb'))
                out_count = conn.execute("SELECT COUNT(*) FROM processed_events").fetchone()[0]
                conn.close()
            except Exception:
                out_count = current_input_count
        else:
            out_count = count_lines_in_dir(out_dir)
            
        dropped = current_input_count - out_count if out_count <= current_input_count else 0
        
        results.append({
            "stage": stage_name,
            "rows_in": current_input_count,
            "rows_out": out_count,
            "dropped": dropped,
            "duration": duration
        })
        
        # Output of this stage is input for next stage
        # Except NLP Enrichment, which only processes text domains, meaning out_count is low.
        # But for Entity Resolution, it reads BOTH NLP and Deduped, so we recalculate input.
        if script_name == "03_dedup_quality.py":
            # Next is NLP, but NLP only reads SOME files.
            # To be accurate, we just measure what NLP outputs vs what it took in.
            # But simple row counts based on dir state is easier.
            current_input_count = out_count 
        elif script_name == "04_nlp_extraction.py":
            # NLP only processed text domains. The real input to 05 is NLP + remaining Deduped
            nlp_count = count_lines_in_dir(BASE_DIR / 'data' / 'processed' / 'nlp_enriched')
            dedup_count = count_lines_in_dir(BASE_DIR / 'data' / 'processed' / 'deduped')
            # Approximation: we know Entity Resolution reads 530 rows
            current_input_count = 530 # Harcoded logic for the demo, or we can dynamically check
            # Let's dynamically check:
            # 05 reads NLP_DOMAINS from nlp_enriched, rest from deduped
            nlp_domains = ['geopolitical', 'policy', 'maritime_logistics', 'procurement']
            input_05 = 0
            for d in ['geopolitical', 'policy', 'maritime_logistics', 'procurement', 'financial', 'market', 'weather_climate', 'inventory', 'refining_downstream', 'historical']:
                if d in nlp_domains:
                    input_05 += count_lines_in_dir(BASE_DIR / 'data' / 'processed' / 'nlp_enriched', f"{d}_*.jsonl")
                else:
                    input_05 += count_lines_in_dir(BASE_DIR / 'data' / 'processed' / 'deduped', f"{d}_*.jsonl")
            current_input_count = input_05
            
            # Fix NLP dropped calculation
            nlp_in = sum([count_lines_in_dir(BASE_DIR / 'data' / 'processed' / 'deduped', f"{d}_*.jsonl") for d in nlp_domains])
            results[-1]["rows_in"] = nlp_in
            results[-1]["dropped"] = nlp_in - out_count if out_count <= nlp_in else 0
        else:
            current_input_count = out_count
            
        logging.info(f"✅ Completed {stage_name} in {duration:.2f}s")
        
    # Print Final Summary Table
    logging.info("\n=================================================================================")
    logging.info(f"{'STAGE NAME':<20} | {'ROWS IN':<10} | {'ROWS OUT':<10} | {'DROPPED':<10} | {'DURATION'}")
    logging.info("---------------------------------------------------------------------------------")
    for r in results:
        logging.info(f"{r['stage']:<20} | {r['rows_in']:<10} | {r['rows_out']:<10} | {r['dropped']:<10} | {r['duration']:.2f}s")
    logging.info("=================================================================================\n")
    logging.info("🚀 Pipeline Part B successfully completed!")

if __name__ == "__main__":
    main()
