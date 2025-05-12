import os
import json
import glob
from binoculars import Binoculars
from tqdm import tqdm
import textwrap
import ijson
import logging
import sys
from pathlib import Path
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Thresholds for prediction
BINOCULARS_ACCURACY_THRESHOLD = 0.9015310749276843  # optimized for f1-score
BINOCULARS_FPR_THRESHOLD = 0.8536432310785527  # optimized for low-fpr [chosen at 0.01%]

def process_file_streaming(input_file, output_file, bino):
    """Process a single JSON file using streaming and save to output location."""
    try:
        logger.info(f"Processing file: {input_file}")
        file_size = os.path.getsize(input_file)
        logger.info(f"File size: {file_size / (1024*1024):.2f} MB")
        
        # First pass: Process items and collect scores
        start_time = time.time()
        processed_items = []
        
        with open(input_file, 'rb') as f:
            items = ijson.items(f, 'item')
            for article in tqdm(items, desc="Processing articles"):
                # Skip if the article already has a Binoculars score
                if "Binoculars_Score" in article and article["Binoculars_Score"] is not None:
                    continue
                
                abstract = article.get("Abstract", "")
                
                # Skip if abstract is empty or N/A
                if not abstract or abstract == "N/A":
                    continue
                
                # Compute the Binoculars score
                try:
                    score = bino.compute_score(abstract)
                    
                    # Determine predictions based on thresholds (0 for Human, 1 for AI)
                    accuracy_prediction = 0 if score >= BINOCULARS_ACCURACY_THRESHOLD else 1
                    fpr_prediction = 0 if score >= BINOCULARS_FPR_THRESHOLD else 1
                    
                    # Store the processed item
                    processed_item = {
                        'Scopus_ID': article.get('Scopus_ID', ''),
                        'Binoculars_Score': score,
                        'Accuracy_Prediction': accuracy_prediction,
                        'FPR_Prediction': fpr_prediction
                    }
                    processed_items.append(processed_item)
                    
                    # Print abstract and results to console
                    logger.info("\n" + "="*80)
                    logger.info(f"Title: {article.get('Title', 'N/A')}")
                    logger.info(f"ID: {article.get('Scopus_ID', 'N/A')}")
                    
                    # Print wrapped abstract for readability
                    logger.info("\nAbstract:")
                    wrapped_abstract = textwrap.fill(abstract, width=80)
                    logger.info(wrapped_abstract)
                    
                    # Print scores and predictions
                    logger.info("\nResults:")
                    logger.info(f"Binoculars Score: {score:.6f}")
                    logger.info(f"Accuracy Prediction: {'Human (0)' if accuracy_prediction == 0 else 'AI-Generated (1)'}")
                    logger.info(f"FPR Prediction: {'Human (0)' if fpr_prediction == 0 else 'AI-Generated (1)'}")
                    logger.info("="*80)
                    
                except Exception as e:
                    logger.error(f"Error processing abstract for {article.get('Scopus_ID', 'N/A')}: {e}")
        
        process_time = time.time() - start_time
        logger.info(f"Processing completed in {process_time:.2f} seconds")
        logger.info(f"Processed {len(processed_items)} items")
        
        if not processed_items:
            logger.warning("No items were processed.")
            return False
        
        # Write to new file
        start_time = time.time()
        
        # Read original file
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Update scores in the original data
        scores_dict = {item['Scopus_ID']: item for item in processed_items}
        for article in data:
            if article.get('Scopus_ID') in scores_dict:
                scores = scores_dict[article['Scopus_ID']]
                article['Binoculars_Score'] = scores['Binoculars_Score']
                article['Accuracy_Prediction'] = scores['Accuracy_Prediction']
                article['FPR_Prediction'] = scores['FPR_Prediction']
        
        # Create output directory if it doesn't exist
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write updated data to new file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        
        write_time = time.time() - start_time
        logger.info(f"File saved to {output_file} in {write_time:.2f} seconds")
        
        return True
    
    except Exception as e:
        logger.error(f"Error processing file {input_file}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def analyze_abstracts():
    """
    Analyze abstracts from specified JSON files using the Binoculars LLM detector,
    and save processed files to data/comp-proc directory.
    """
    # Initialize Binoculars
    bino = Binoculars()
    
    # Files to process
    target_files = [
        "2021/APRIL_comp_2021.json",
        "2021/FEBRUARY_comp_2021.json",
        "2021/NOVEMBER_comp_2021.json",
        "2022/APRIL_comp_2022.json",
        "2022/AUGUST_comp_2022.json",
        "2022/FEBRUARY_comp_2022.json",
        "2022/JANUARY_comp_2022.json",
        "2022/JULY_comp_2022.json",
        "2022/JUNE_comp_2022.json",
        "2022/MARCH_comp_2022.json",
        "2022/MAY_comp_2022.json",
        "2022/NOVEMBER_comp_2022.json",
        "2022/OCTOBER_comp_2022.json",
        "2022/SEPTEMBER_comp_2022.json"
    ]
    
    # Input and output directories
    input_dir = Path("data/comp/pre")
    output_dir = Path("data/comp-proc")
    
    success_count = 0
    for file_path in target_files:
        input_file = input_dir / file_path
        output_file = output_dir / file_path
        
        if not input_file.exists():
            logger.error(f"Input file not found: {input_file}")
            continue
        
        logger.info(f"\nProcessing: {file_path}")
        if process_file_streaming(input_file, output_file, bino):
            success_count += 1
    
    logger.info(f"\nProcessing completed:")
    logger.info(f"Successfully processed {success_count} out of {len(target_files)} files")

if __name__ == "__main__":
    analyze_abstracts() 