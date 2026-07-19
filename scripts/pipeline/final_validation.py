#!/usr/bin/env python3
import os
import sys
import json
import yaml
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_FILE = BASE_DIR / 'logs' / 'final_validation_report.json'
DOCS_DIR = BASE_DIR / 'docs'
DOCS_DIR.mkdir(exist_ok=True)
REPORT_FILE = DOCS_DIR / 'VALIDATION_REPORT.md'

DOMAINS = [
    'geopolitical', 'policy', 'maritime_logistics', 'procurement',
    'financial', 'market', 'weather_climate', 'inventory',
    'refining_downstream', 'historical'
]

REQUIRED_RAW_FIELDS = {'source', 'domain', 'timestamp_utc', 'url'}

# Track overall status
all_passed = True
failures = []

def log_fail(msg):
    global all_passed
    all_passed = False
    failures.append(msg)
    print(f"❌ FAIL: {msg}")

def check_stage_1_part_a():
    print("\n--- STAGE 1: Part A Source Coverage ---")
    results = {}
    forty_eight_hours_ago = datetime.now(timezone.utc) - timedelta(hours=48)
    
    for domain in DOMAINS:
        domain_dir = BASE_DIR / 'data' / 'raw' / domain
        status = 'FAIL'
        rows = 0
        valid_schema_count = 0
        freshest_dt = None
        
        if domain_dir.exists():
            for p in domain_dir.rglob("*.jsonl"):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        for line in f:
                            if not line.strip(): continue
                            rows += 1
                            try:
                                record = json.loads(line)
                                # Check schema
                                has_required = all(k in record for k in REQUIRED_RAW_FIELDS)
                                has_value = 'raw_text' in record or 'raw_value' in record
                                if has_required and has_value:
                                    valid_schema_count += 1
                                    
                                # Check timestamp
                                ts_str = record.get('timestamp_utc')
                                if ts_str:
                                    try:
                                        # Parse and force UTC timezone
                                        ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                        if ts.tzinfo is None:
                                            ts = ts.replace(tzinfo=timezone.utc)
                                        if freshest_dt is None or ts > freshest_dt:
                                            freshest_dt = ts
                                    except ValueError:
                                        pass
                            except json.JSONDecodeError:
                                pass
                except Exception:
                    pass
                    
        schema_pct = (valid_schema_count / rows * 100) if rows > 0 else 0
        
        if rows == 0:
            status = 'EMPTY'
            log_fail(f"Domain '{domain}' has 0 raw rows.")
        elif schema_pct < 100:
            log_fail(f"Domain '{domain}' schema valid % is {schema_pct:.1f}%")
        elif freshest_dt is None or freshest_dt < forty_eight_hours_ago:
            log_fail(f"Domain '{domain}' has stale data. Freshest: {freshest_dt}")
        else:
            status = 'PASS'
            
        freshest_str = freshest_dt.strftime("%Y-%m-%d %H:%M") if freshest_dt else "N/A"
        print(f"{domain:<20} | {rows:<6} | {schema_pct:6.1f}% | {freshest_str:<16} | {status}")
        
        results[domain] = {
            "rows": rows,
            "schema_valid_pct": schema_pct,
            "freshest_record": freshest_str,
            "status": status
        }
    return results

def count_lines(domain, stage_dir):
    path = BASE_DIR / 'data' / 'processed' / stage_dir
    total = 0
    if not path.exists():
        return total
    for p in path.rglob(f"{domain}_*.jsonl"):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                total += sum(1 for line in f if line.strip())
        except Exception:
            pass
    return total

def check_stage_2_part_b(raw_counts):
    print("\n--- STAGE 2: Part B Pipeline Integrity ---")
    results = {}
    
    print(f"{'DOMAIN':<20} | {'RAW':<5} | {'NORM':<5} | {'DEDUP':<5} | {'NLP':<5} | {'ENTITY':<6}")
    
    for domain in DOMAINS:
        c_raw = raw_counts[domain]["rows"]
        c_norm = count_lines(domain, 'normalized')
        c_dedup = count_lines(domain, 'deduped')
        c_nlp = count_lines(domain, 'nlp_enriched') if domain in ['geopolitical', 'policy', 'maritime_logistics', 'procurement'] else '-'
        c_entity = count_lines(domain, 'entity_resolved')
        
        print(f"{domain:<20} | {c_raw:<5} | {c_norm:<5} | {c_dedup:<5} | {str(c_nlp):<5} | {c_entity:<6}")
        
        # Validation checks
        if c_raw > 0 and c_entity == 0:
            log_fail(f"Domain '{domain}' dropped to 0 by the end of the pipeline.")
            
        if c_norm > c_raw:
            log_fail(f"Domain '{domain}' normalized > raw ({c_norm} > {c_raw})")
        if c_dedup > c_norm:
            log_fail(f"Domain '{domain}' deduped > normalized ({c_dedup} > {c_norm})")
            
        if isinstance(c_nlp, int):
            if c_nlp > c_dedup:
                log_fail(f"Domain '{domain}' nlp > deduped ({c_nlp} > {c_dedup})")
            if c_entity > c_nlp:
                log_fail(f"Domain '{domain}' entity > nlp ({c_entity} > {c_nlp})")
        else:
            if c_entity > c_dedup:
                log_fail(f"Domain '{domain}' entity > deduped ({c_entity} > {c_dedup})")
                
        results[domain] = {
            "raw": c_raw, "norm": c_norm, "dedup": c_dedup, "nlp": c_nlp, "entity": c_entity
        }
    return results

def check_stage_3_datalake():
    print("\n--- STAGE 3: Data Lake Check ---")
    db_file = BASE_DIR / 'data' / 'datalake' / 'energy_resilience.duckdb'
    if not db_file.exists():
        log_fail("DuckDB file not found.")
        return {}
        
    try:
        conn = duckdb.connect(str(db_file))
        
        tables = conn.execute("SHOW TABLES").fetchall()
        table_names = [t[0] for t in tables]
        
        for t in ['raw_events', 'processed_events']:
            if t not in table_names:
                log_fail(f"Table '{t}' missing from DuckDB.")
            else:
                cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                if cnt == 0:
                    log_fail(f"Table '{t}' is empty.")
                print(f"Table '{t}' exists with {cnt} rows.")
                
        views = ['v_daily_domain_counts', 'v_high_urgency_events', 'v_chokepoint_activity']
        view_results = {}
        for v in views:
            if v not in table_names:
                log_fail(f"View '{v}' missing from DuckDB.")
                continue
            cnt = conn.execute(f"SELECT COUNT(*) FROM {v}").fetchone()[0]
            print(f"\nView '{v}' has {cnt} rows. Sample (5 rows):")
            sample = conn.execute(f"SELECT * FROM {v} LIMIT 5").fetchdf()
            print(sample.to_string(index=False))
            view_results[v] = cnt
            
        conn.close()
        return {"tables_exist": True, "views": view_results}
    except Exception as e:
        log_fail(f"DuckDB check failed: {e}")
        return {"tables_exist": False}

def check_stage_4_governance():
    print("\n--- STAGE 4: Config & Governance Checks ---")
    results = {}
    
    # Check sources.yaml
    sources_yaml = BASE_DIR / 'config' / 'sources.yaml'
    if not sources_yaml.exists():
        log_fail("sources.yaml missing.")
    else:
        with open(sources_yaml, 'r') as f:
            cfg = yaml.safe_load(f)
            missing = []
            for d in DOMAINS:
                if d not in cfg:
                    missing.append(d)
                elif not any('last_successful_run' in source for source in cfg[d]):
                    log_fail(f"Domain '{d}' missing last_successful_run in sources.yaml")
            if missing:
                log_fail(f"Missing domains in sources.yaml: {missing}")
            else:
                print("sources.yaml complete.")
                
    # Check entity files
    for f in ['entity_aliases.yaml', 'energy_entities.yaml']:
        p = BASE_DIR / 'config' / f
        if not p.exists() or p.stat().st_size == 0:
            log_fail(f"{f} is missing or empty.")
        else:
            print(f"{f} exists and populated.")
            
    # Check .gitignore
    gitignore = BASE_DIR / '.gitignore'
    if not gitignore.exists() or '.env' not in gitignore.read_text():
        log_fail(".env not in .gitignore")
    else:
        print(".env properly gitignored.")
        
    # Check secrets
    key_pattern = re.compile(r'(api_key|secret|token)\s*=\s*[\'"][a-zA-Z0-9_-]{10,}[\'"]', re.IGNORECASE)
    secrets_found = False
    for p in BASE_DIR.rglob("*.py"):
        try:
            content = p.read_text(encoding='utf-8')
            if key_pattern.search(content):
                log_fail(f"Hardcoded secret found in {p.name}")
                secrets_found = True
        except Exception:
            pass
    if not secrets_found:
        print("No hardcoded secrets found in .py files.")
        
    results["governance_passed"] = not secrets_found
    return results

def check_stage_5_limitations():
    print("\n--- STAGE 5: Known-Limitation Disclosure ---")
    
    fin_py = BASE_DIR / 'scripts' / 'ingestion' / 'financial.py'
    readme = BASE_DIR / 'README.md'
    
    limitation_term = "SWIFT"
    
    if fin_py.exists():
        if limitation_term.lower() not in fin_py.read_text().lower():
            log_fail(f"financial.py missing limitation disclosure for {limitation_term}")
        else:
            print("financial.py discloses limitation.")
    else:
        log_fail("financial.py missing.")
        
    if readme.exists():
        if limitation_term.lower() not in readme.read_text().lower():
            log_fail(f"README.md missing limitation disclosure for {limitation_term}")
        else:
            print("README.md discloses limitation.")
    else:
        log_fail("README.md missing.")
        
    return {"limitation_disclosed": True}

def main():
    print("=========================================")
    print("      FINAL END-TO-END VALIDATION        ")
    print("=========================================")
    
    stage_1 = check_stage_1_part_a()
    stage_2 = check_stage_2_part_b(stage_1)
    stage_3 = check_stage_3_datalake()
    stage_4 = check_stage_4_governance()
    stage_5 = check_stage_5_limitations()
    
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": "READY FOR REVIEW" if all_passed else "NOT READY — see failures below",
        "failures": failures,
        "details": {
            "stage_1_coverage": stage_1,
            "stage_2_pipeline": stage_2,
            "stage_3_datalake": stage_3,
            "stage_4_governance": stage_4,
            "stage_5_limitations": stage_5
        }
    }
    
    with open(LOG_FILE, 'w') as f:
        json.dump(report, f, indent=4)
        
    # Generate Markdown Report
    with open(REPORT_FILE, 'w') as f:
        f.write(f"# Final Validation Report\n\n")
        f.write(f"**Verdict:** {report['verdict']}\n\n")
        
        if failures:
            f.write("### Failures:\n")
            for fail in failures:
                f.write(f"- ❌ {fail}\n")
            f.write("\n---\n")
            
        f.write("### Part B Pipeline Funnel\n")
        f.write("| Domain | Raw | Norm | Dedup | NLP | Entity |\n")
        f.write("|--------|-----|------|-------|-----|--------|\n")
        for dom, counts in stage_2.items():
            f.write(f"| {dom} | {counts['raw']} | {counts['norm']} | {counts['dedup']} | {counts['nlp']} | {counts['entity']} |\n")
            
    print("\n=========================================")
    if all_passed:
        print("✅ VERDICT: READY FOR REVIEW")
    else:
        print("❌ VERDICT: NOT READY — see failures below")
        for f in failures:
            print(f"  - {f}")
    print("=========================================")
    print(f"Reports saved to:\n - {LOG_FILE}\n - {REPORT_FILE}")

if __name__ == "__main__":
    main()
