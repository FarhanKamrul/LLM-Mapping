import os
import requests
import json
import time
import random
import glob
import sys
import select
from dotenv import load_dotenv
from datetime import datetime, timedelta

import pybliometrics
pybliometrics.scopus.init()

# ==============================
# 🔹 Load API Key(s) from .env file
# ==============================
load_dotenv()
api_keys_str = os.getenv("SCOPUS_API_KEYS")
if api_keys_str:
    API_KEYS = [key.strip() for key in api_keys_str.split(",")]
else:
    API_KEYS = [os.getenv("SCOPUS_API_KEY")]

# Global pointer for current API key
current_api_key_index = 0

def get_headers():
    return {
        "X-ELS-APIKey": API_KEYS[current_api_key_index],
        "Accept": "application/json"
    }

def cycle_api_key():
    global current_api_key_index
    current_api_key_index = (current_api_key_index + 1) % len(API_KEYS)
    print(f"Cycling to API key index {current_api_key_index}: {API_KEYS[current_api_key_index]}")

def check_for_pause():
    # Non-blocking check for user input on stdin.
    # If the user types 'P' (or 'p') and presses Enter, return True.
    rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
    if rlist:
        line = sys.stdin.readline().strip()
        if line.lower() == 'p':
            return True
    return False

def pause_and_reload():
    print("Pausing execution. Add new API keys to the .env file and press 'P' again to resume.")
    while True:
        if check_for_pause():
            break
        time.sleep(1)
    print("Resuming execution. Reloading API keys from .env.")
    load_dotenv()
    new_keys_str = os.getenv("SCOPUS_API_KEYS")
    if new_keys_str:
        global API_KEYS
        API_KEYS = [key.strip() for key in new_keys_str.split(",")]
        print(f"New API keys loaded: {API_KEYS}")

# ==============================
# 🔹 API Endpoints & Global Query Parameters
# ==============================
SEARCH_URL = "https://api.elsevier.com/content/search/scopus"
ABSTRACT_URL = "https://api.elsevier.com/content/abstract/scopus_id/"
COUNT = 200  # Articles per API call set to 200

# ==============================
# 🔹 Functions to Fetch Data
# ==============================
def fetch_metadata(scopus_id, retries=3):
    """Retrieve full metadata including abstract and affiliations safely."""
    for attempt in range(retries):
        print(f"Fetching metadata for {scopus_id} (attempt {attempt+1})...")
        response = requests.get(f"{ABSTRACT_URL}{scopus_id}", headers=get_headers())
        if response.status_code == 429:
            print(f"Rate limit hit for {scopus_id}. Cycling API key...")
            cycle_api_key()
            time.sleep(2)
            continue
        try:
            json_data = response.json()
        except Exception as e:
            print(f"Error parsing JSON for {scopus_id}: {e}")
            cycle_api_key()
            time.sleep(2)
            continue
        if not json_data or "abstracts-retrieval-response" not in json_data:
            print(f"Error: No abstracts-retrieval-response found for {scopus_id}")
            cycle_api_key()
            time.sleep(2)
            continue
        data = json_data["abstracts-retrieval-response"]
        core_data = data.get("coredata", {})
        authors_section = data.get("authors") or {}
        authors = authors_section.get("author", [])
        affiliations = data.get("affiliation", [])
        if not isinstance(affiliations, list):
            affiliations = [affiliations] if affiliations else []
        affiliation_name = affiliations[0].get("affiliation-name", "N/A") if affiliations else "N/A"
        affiliation_country = affiliations[0].get("affiliation-country", "N/A") if affiliations else "N/A"
        return {
            "Scopus_ID": scopus_id,
            "Title": core_data.get("dc:title", "N/A"),
            "Abstract": core_data.get("dc:description", "N/A"),
            "Authors": [author.get("ce:indexed-name", "N/A") for author in authors] if isinstance(authors, list) else [],
            "Affiliation_Name": affiliation_name,
            "Affiliation_Country": affiliation_country,
            "Publication_Date": core_data.get("prism:coverDate", "N/A"),
            "DOI": core_data.get("prism:doi", "N/A"),
            "Keywords": core_data.get("authkeywords", "N/A"),
            "Cited_By_Count": int(core_data.get("citedby-count", 0)),
            "Source": core_data.get("prism:publicationName", "N/A")
        }
    return None

def fetch_abstract(scopus_id, retries=3):
    """Retrieve the abstract for a given article."""
    for attempt in range(retries):
        response = requests.get(f"{ABSTRACT_URL}{scopus_id}", headers=get_headers())
        if response.status_code == 429:
            print(f"Rate limit hit for abstract {scopus_id}. Cycling API key...")
            cycle_api_key()
            time.sleep(2)
            continue
        try:
            json_data = response.json()
        except Exception as e:
            print(f"Error parsing JSON for abstract of {scopus_id}: {e}")
            cycle_api_key()
            time.sleep(2)
            continue
        if not json_data or "abstracts-retrieval-response" not in json_data:
            print(f"Error: No abstracts-retrieval-response found for abstract of {scopus_id}")
            cycle_api_key()
            time.sleep(2)
            continue
        data = json_data["abstracts-retrieval-response"]
        return data.get("coredata", {}).get("dc:description", "N/A")
    return "N/A"

def fetch_citations(scopus_id, count=200, retries=3):
    """
    Retrieve citing article IDs using a REF(scopus_id) query,
    and also extract the citation count and affiliation-country for each citing article.
    """
    query = f"REF({scopus_id})"
    params = {"query": query, "count": count, "start": 0, "view": "STANDARD"}
    for attempt in range(retries):
        response = requests.get(SEARCH_URL, headers=get_headers(), params=params)
        if response.status_code == 429:
            print(f"Rate limit hit for citations of {scopus_id}. Cycling API key...")
            cycle_api_key()
            time.sleep(2)
            continue
        try:
            json_data = response.json()
        except Exception as e:
            print(f"Error parsing JSON for citations of {scopus_id}: {e}")
            cycle_api_key()
            time.sleep(2)
            continue
        if not json_data or "search-results" not in json_data:
            print(f"Error: No search-results found for citations of {scopus_id}")
            cycle_api_key()
            time.sleep(2)
            continue
        entries = json_data.get("search-results", {}).get("entry", [])
        citations = []
        for entry in entries:
            citing_id = entry.get("dc:identifier", "").replace("SCOPUS_ID:", "")
            citing_url = entry.get("prism:url", "N/A")
            cited_date = entry.get("prism:coverDate", "N/A")
            # Extract additional fields from the entry if available:
            citing_citation_count = entry.get("citedby-count", "N/A")
            affiliation_info = entry.get("affiliation", {})
            if isinstance(affiliation_info, list) and affiliation_info:
                citing_aff_country = affiliation_info[0].get("affiliation-country", "N/A")
            elif isinstance(affiliation_info, dict):
                citing_aff_country = affiliation_info.get("affiliation-country", "N/A")
            else:
                citing_aff_country = "N/A"
            citations.append({
                "Citing_Article_Scopus_ID": citing_id,
                "Citing_Article_URL": citing_url,
                "Cited_Date": cited_date,
                "Citing_Citation_Count": citing_citation_count,
                "Citing_Affiliation_Country": citing_aff_country
            })
        return {"citations": citations}
    return {"citations": []}

def backup_data(data, backup_filename):
    """Save a backup of data to the specified file."""
    with open(backup_filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    print(f"Backup saved: {backup_filename}")

# ==============================
# 🔹 Ensure Backup Directory Structure Exists
# ==============================
BACKUP_INTERVAL = 500  # Reduced backup frequency to 500 articles
base_backup_dir = "data/comp/post/"
os.makedirs(base_backup_dir, exist_ok=True)

def get_year_folder(year):
    year_folder = os.path.join(base_backup_dir, str(year))
    os.makedirs(year_folder, exist_ok=True)
    return year_folder

# ==============================
# 🔹 Resume from Last Backup (per month) if Available
# ==============================
def resume_backup(year_dir, month):
    backup_files = glob.glob(os.path.join(year_dir, f"{month}_*_comp_23_25.json"))
    start_offset = 0
    articles = []
    if backup_files:
        indices = []
        for bf in backup_files:
            base = os.path.basename(bf)
            try:
                # Expected format: MONTH_<number>_comp_23_25.json
                index_val = int(base.split("_")[1])
                indices.append(index_val)
            except Exception as e:
                print(f"Error extracting index from {base}: {e}")
        if indices:
            start_offset = max(indices)
            latest_backup = os.path.join(year_dir, f"{month}_{start_offset}_comp_23_25.json")
            with open(latest_backup, "r", encoding="utf-8") as f:
                articles = json.load(f)
            print(f"Resuming {month} from backup: {start_offset} articles processed.")
    else:
        print(f"No backup found for {month}. Starting fresh.")
    return start_offset, articles

# ==============================
# 🔹 Main Data Collection Loop: Month-by-Month
# ==============================
# Only process May and July 2023
target_months = {
    "2023": ["MAY", "JULY"]
}

for year, months in target_months.items():
    year_dir = get_year_folder(year)
    for month in months:
        print(f"\nProcessing {month} {year}...")
        
        # Resume from last backup if available
        start_offset, articles = resume_backup(year_dir, month)
        
        # Set up the date range for the month
        if month == "MAY":
            month_name = "May"
        else:  # JULY
            month_name = "July"
        
        # Construct the query for computer science articles
        query = f"SUBJAREA(COMP) AND PUBDATETXT({month_name}+{year})"
        
        # Fetch articles
        params = {
            "query": query,
            "count": COUNT,
            "start": start_offset,
            "view": "STANDARD"
        }
        
        while True:
            if check_for_pause():
                pause_and_reload()
            
            response = requests.get(SEARCH_URL, headers=get_headers(), params=params)
            
            if response.status_code == 429:
                print("Rate limit hit. Cycling API key...")
                cycle_api_key()
                time.sleep(2)
                continue
            
            try:
                json_data = response.json()
            except Exception as e:
                print(f"Error parsing JSON: {e}")
                cycle_api_key()
                time.sleep(2)
                continue
            
            if not json_data or "search-results" not in json_data:
                print("Error: No search-results found")
                # Save whatever articles we have collected so far
                if articles:
                    backup_filename = os.path.join(year_dir, f"{month}_{len(articles)}_comp_23_25.json")
                    backup_data(articles, backup_filename)
                    print(f"Saved {len(articles)} articles collected so far")
                cycle_api_key()
                time.sleep(2)
                break  # Exit the while loop since we've hit an error
            
            entries = json_data.get("search-results", {}).get("entry", [])
            if not entries:
                # No more entries found, save what we have
                if articles:
                    backup_filename = os.path.join(year_dir, f"{month}_{len(articles)}_comp_23_25.json")
                    backup_data(articles, backup_filename)
                    print(f"Completed processing {month} {year}. Total articles: {len(articles)}")
                break
            
            for entry in entries:
                scopus_id = entry.get("dc:identifier", "").replace("SCOPUS_ID:", "")
                if not scopus_id:
                    continue
                
                # Fetch metadata
                metadata = fetch_metadata(scopus_id)
                if not metadata:
                    continue
                
                # Add to articles list
                articles.append(metadata)
                
                # Backup every BACKUP_INTERVAL articles
                if len(articles) % BACKUP_INTERVAL == 0:
                    backup_filename = os.path.join(year_dir, f"{month}_{len(articles)}_comp_23_25.json")
                    backup_data(articles, backup_filename)
            
            # Update start parameter for next batch
            params["start"] += COUNT
            
            # Add a small delay between requests
            time.sleep(1)
        
        # Save final backup
        if articles:
            backup_filename = os.path.join(year_dir, f"{month}_{len(articles)}_comp_23_25.json")
            backup_data(articles, backup_filename)
        
        print(f"Completed processing {month} {year}. Total articles: {len(articles)}")

print("\nData collection completed for May and July 2023.") 