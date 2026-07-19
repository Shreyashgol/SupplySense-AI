#!/usr/bin/env python3
import os
import sys
import json
import yaml
import logging
import spacy
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from pathlib import Path

# Setup Logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(log_dir / 'nlp_extraction.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

DEDUPED_DIR = BASE_DIR / 'data' / 'processed' / 'deduped'
ENRICHED_DIR = BASE_DIR / 'data' / 'processed' / 'nlp_enriched'
ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
EVENT_YAML = BASE_DIR / 'config' / 'event_keywords.yaml'

TARGET_DOMAINS = ['geopolitical', 'policy', 'maritime_logistics', 'procurement']

URGENCY_KEYWORDS = [
    "closure", "attack", "sanction", "restriction", "halt", "embargo",
    "disruption", "explosion", "ban", "strike", "blockade", "hijack",
    "crisis", "emergency", "force majeure", "critical"
]

def load_event_dict():
    if not EVENT_YAML.exists():
        logging.warning("Event keyword config not found, defaulting to empty.")
        return {}
    with open(EVENT_YAML, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config

def batched(iterable, n):
    """Yield successive n-sized chunks from iterable."""
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) == n:
            yield batch
            batch = []
    if batch:
        yield batch

def calculate_urgency(text):
    text_lower = str(text).lower()
    hits = sum(1 for word in URGENCY_KEYWORDS if word in text_lower)
    # Simple normalization: 0 to 1 based on max expected hits (e.g., 3+ hits = 1.0)
    score = min(hits / 3.0, 1.0)
    return round(score, 2)

def categorize_event(text, event_dict):
    text_lower = str(text).lower()
    category_scores = {}
    
    for category, keywords in event_dict.items():
        hits = sum(1 for kw in keywords if kw.lower() in text_lower)
        if hits > 0:
            category_scores[category] = hits
            
    if not category_scores:
        return "general_update"
        
    # Return the category with the highest hits
    return max(category_scores, key=category_scores.get)

def process_file(file_path, nlp, vader, event_dict):
    domain = file_path.name.split('_deduped')[0]
    out_file = ENRICHED_DIR / f"{domain}_enriched.jsonl"
    
    total_processed = 0
    
    try:
        # Read the entire file as a generator to keep memory low
        def record_generator():
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        yield json.loads(line)
        
        # Open output file in write mode initially to clear it, then append in batches
        with open(out_file, 'w', encoding='utf-8') as out_f:
            for batch in batched(record_generator(), 200):
                for row in batch:
                    raw_text = row.get('raw_text', '')
                    if not isinstance(raw_text, str) or not raw_text.strip():
                        row['entities'] = []
                        row['sentiment_score'] = 0.0
                        row['urgency_score'] = 0.0
                        row['event_category'] = "general_update"
                    else:
                        # 1. Named Entities
                        doc = nlp(raw_text)
                        # Filter for specific entity types
                        allowed_ents = {'ORG', 'GPE', 'LOC', 'DATE'}
                        entities = [
                            {"text": ent.text, "label": ent.label_}
                            for ent in doc.ents if ent.label_ in allowed_ents
                        ]
                        
                        # 2. Sentiment
                        sentiment = vader.polarity_scores(raw_text)
                        
                        # 3. Urgency
                        urgency = calculate_urgency(raw_text)
                        
                        # 4. Event Categorization
                        event_cat = categorize_event(raw_text, event_dict)
                        
                        # Attach metadata
                        row['entities'] = entities
                        row['sentiment_score'] = sentiment['compound']
                        row['urgency_score'] = urgency
                        row['event_category'] = event_cat
                        
                    # Write immediately
                    json.dump(row, out_f)
                    out_f.write('\n')
                    total_processed += 1
                    
        logging.info(f"Enriched {total_processed} rows for domain {domain}")
        return total_processed
        
    except Exception as e:
        logging.error(f"Failed processing {file_path}: {e}")
        return 0

def main():
    logging.info("Starting NLP Enrichment Pipeline...")
    
    # Load Models
    try:
        logging.info("Loading spaCy model (en_core_web_sm)...")
        nlp = spacy.load("en_core_web_sm")
        logging.info("Loading NLTK VADER...")
        vader = SentimentIntensityAnalyzer()
    except Exception as e:
        logging.error(f"Failed to load NLP models: {e}. Please ensure they are downloaded.")
        sys.exit(1)
        
    event_dict = load_event_dict()
    
    total_enriched = 0
    
    # Process only target domains
    for domain in TARGET_DOMAINS:
        file_path = DEDUPED_DIR / f"{domain}_deduped.jsonl"
        if file_path.exists():
            total_enriched += process_file(file_path, nlp, vader, event_dict)
        else:
            logging.warning(f"Domain file {file_path} not found, skipping.")
            
    logging.info(f"NLP Enrichment complete. Total rows enriched: {total_enriched}.")

if __name__ == "__main__":
    main()
