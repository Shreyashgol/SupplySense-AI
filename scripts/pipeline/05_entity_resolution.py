#!/usr/bin/env python3
import os
import sys
import json
import yaml
import uuid
import logging
import pandas as pd
from pathlib import Path
from datetime import timedelta

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(log_dir / 'entity_resolution.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

DEDUPED_DIR = BASE_DIR / 'data' / 'processed' / 'deduped'
NLP_DIR = BASE_DIR / 'data' / 'processed' / 'nlp_enriched'
RESOLVED_DIR = BASE_DIR / 'data' / 'processed' / 'entity_resolved'
RESOLVED_DIR.mkdir(parents=True, exist_ok=True)

ENTITY_ALIASES_YAML = BASE_DIR / 'config' / 'entity_aliases.yaml'
ENERGY_ENTITIES_YAML = BASE_DIR / 'config' / 'energy_entities.yaml'

NLP_DOMAINS = ['geopolitical', 'policy', 'maritime_logistics', 'procurement']

def load_gazetteers():
    alias_map = {}
    geo_map = {}
    
    # 1. Load general aliases (from B2)
    if ENTITY_ALIASES_YAML.exists():
        with open(ENTITY_ALIASES_YAML, 'r', encoding='utf-8') as f:
            general = yaml.safe_load(f) or {}
            for canonical, aliases in general.items():
                alias_map[canonical.lower()] = canonical
                for alias in aliases:
                    alias_map[alias.lower()] = canonical
                    
    # 2. Load energy specific gazetteer
    if ENERGY_ENTITIES_YAML.exists():
        with open(ENERGY_ENTITIES_YAML, 'r', encoding='utf-8') as f:
            energy = yaml.safe_load(f) or {}
            for canonical, data in energy.items():
                if not data:
                    continue
                alias_map[canonical.lower()] = canonical
                for alias in data.get('aliases', []):
                    alias_map[alias.lower()] = canonical
                    
                if 'lat' in data and 'lon' in data:
                    geo_map[canonical] = {
                        "name": canonical,
                        "type": data.get("type", "unknown"),
                        "lat": data["lat"],
                        "lon": data["lon"]
                    }
                    
    return alias_map, geo_map

def resolve_entities_for_row(row, alias_map, geo_map):
    raw_ents = set()
    
    # Check NLP entities
    if 'entities' in row:
        for ent in row['entities']:
            raw_ents.add(ent.get('text', ''))
            
    # Check region field
    if 'region' in row and row['region']:
        raw_ents.add(str(row['region']))
        
    resolved = set()
    geo_tags = []
    
    for raw in raw_ents:
        if not raw: continue
        raw_lower = raw.lower().strip()
        # Direct match
        if raw_lower in alias_map:
            canonical = alias_map[raw_lower]
            if canonical not in resolved:
                resolved.add(canonical)
                if canonical in geo_map:
                    geo_tags.append(geo_map[canonical])
        else:
            # Token match (e.g., if "Aramco" is in "Saudi Aramco facility")
            for alias_key, canonical in alias_map.items():
                if alias_key in raw_lower: # Substring match
                    if canonical not in resolved:
                        resolved.add(canonical)
                        if canonical in geo_map:
                            geo_tags.append(geo_map[canonical])
                            
    row['resolved_entities'] = list(resolved)
    row['geo_tags'] = geo_tags
    return row

def build_48h_clusters(all_records):
    """
    Groups records by their first resolved entity.
    Within each entity group, records within 48 hours of each other get the same linked_event_id.
    """
    if not all_records:
        return
        
    df = pd.DataFrame(all_records)
    if 'timestamp_utc' not in df.columns or df.empty:
        return
        
    df['date_parsed'] = pd.to_datetime(df['timestamp_utc'], errors='coerce')
    
    # We will track linked_event_id in a separate mapping
    # row_id -> linked_event_id
    id_mapping = {}
    
    # Explode by resolved entities so a row can participate in clustering for ANY of its entities
    df_exp = df.explode('resolved_entities')
    df_exp = df_exp.dropna(subset=['resolved_entities', 'date_parsed'])
    
    if df_exp.empty:
        return
        
    for entity, group in df_exp.groupby('resolved_entities'):
        group = group.sort_values('date_parsed')
        current_cluster_id = None
        last_time = None
        
        for _, row in group.iterrows():
            row_id = row['_row_id']
            curr_time = row['date_parsed']
            
            if last_time is None or (curr_time - last_time) > pd.Timedelta(hours=48):
                current_cluster_id = str(uuid.uuid4())
                
            # If the row doesn't have an ID yet, assign it
            # If it does, we just keep the first one assigned (primary entity cluster)
            if row_id not in id_mapping:
                id_mapping[row_id] = current_cluster_id
                
            last_time = curr_time
            
    # Assign back to the records list
    for record in all_records:
        r_id = record.get('_row_id')
        if r_id in id_mapping:
            record['linked_event_id'] = id_mapping[r_id]
        else:
            # Give it a standalone UUID if it didn't cluster
            record['linked_event_id'] = str(uuid.uuid4())

def main():
    logging.info("Starting Entity Resolution & Clustering Pipeline...")
    
    alias_map, geo_map = load_gazetteers()
    logging.info(f"Loaded {len(alias_map)} entity aliases and {len(geo_map)} geo-tagged entities.")
    
    all_records = []
    domain_files = {}
    
    # Discover files
    for domain in ['geopolitical', 'policy', 'maritime_logistics', 'procurement', 'financial', 'market', 'weather_climate', 'inventory', 'refining_downstream', 'historical']:
        # Decide which directory to pull from
        if domain in NLP_DOMAINS:
            file_path = NLP_DIR / f"{domain}_enriched.jsonl"
        else:
            file_path = DEDUPED_DIR / f"{domain}_deduped.jsonl"
            
        if file_path.exists():
            domain_files[domain] = file_path
        else:
            logging.warning(f"Domain file {file_path} not found. Skipping.")
            
    # Read all into memory
    for domain, path in domain_files.items():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip(): continue
                    row = json.loads(line)
                    row['_row_id'] = str(uuid.uuid4()) # Temporary ID for clustering mapping
                    row = resolve_entities_for_row(row, alias_map, geo_map)
                    # We ensure we have the domain to split it back later
                    row['_domain'] = domain 
                    all_records.append(row)
        except Exception as e:
            logging.error(f"Failed reading {path}: {e}")
            
    logging.info(f"Loaded {len(all_records)} total records into memory for cross-domain clustering.")
    
    # Build the 48-hour clusters
    build_48h_clusters(all_records)
    
    # Write back to domain files
    # We will write to data/processed/entity_resolved/
    write_counts = {}
    for record in all_records:
        domain = record.pop('_domain', 'unknown')
        record.pop('_row_id', None) # Remove temp ID
        
        out_file = RESOLVED_DIR / f"{domain}_resolved.jsonl"
        
        mode = 'a' if domain in write_counts else 'w'
        with open(out_file, mode, encoding='utf-8') as out_f:
            json.dump(record, out_f)
            out_f.write('\n')
            
        write_counts[domain] = write_counts.get(domain, 0) + 1
        
    for d, count in write_counts.items():
        logging.info(f"Resolved & Clustered {count} rows for domain {d}")
        
    logging.info("Entity Resolution & Clustering complete.")

if __name__ == "__main__":
    main()
