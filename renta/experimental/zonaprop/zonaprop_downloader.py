"""
Zonaprop HTML downloader utility - implements the successful notebook approach.

This module provides functions to download Zonaprop pages manually using cloudscraper,
which can then be used as fallback when direct scraping fails due to anti-bot protection.
"""

import os
import re
import time
from pathlib import Path
from typing import List, Optional
import cloudscraper
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import structlog

logger = structlog.get_logger(__name__)


def download_zonaprop_pages(
    search_url: str, 
    folder_path: str, 
    overwrite: bool = False,
    delay: int = 30
) -> List[str]:
    """
    Download Zonaprop search result pages as HTML files.
    
    This function replicates the successful approach from the notebook:
    - Uses cloudscraper with delay to avoid 403 errors
    - Downloads all pages from a search URL
    - Saves each page as a separate HTML file
    
    Args:
        search_url: Zonaprop search URL to download
        folder_path: Directory to save HTML files
        overwrite: Whether to overwrite existing files
        delay: Delay between requests (seconds)
        
    Returns:
        List of downloaded file paths
        
    Raises:
        Exception: If download fails
    """
    logger.info("Starting Zonaprop page download", url=search_url, folder=folder_path)
    
    # Create cloudscraper instance with proper browser emulation
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    # Create directory if it doesn't exist
    os.makedirs(folder_path, exist_ok=True)
    
    # If overwrite is True, remove existing files
    if overwrite:
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        logger.info("Existing files removed", folder=folder_path)
    
    # First request to get total number of pages
    logger.info("Fetching first page to determine total pages")
    res = scraper.get(search_url)
    if res.status_code != 200:
        raise Exception(f'Error fetching first page: {res.status_code}')
    
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # Find total pages from script tag
    total_pages = None
    for script in soup.find_all('script'):
        if script.string and 'totalPages' in script.string:
            match = re.search(r'"totalPages":(\d+)', script.string)
            if match:
                total_pages = int(match.group(1))
                break
    
    if not total_pages:
        logger.warning("Could not find total pages, assuming 1 page")
        total_pages = 1
    
    logger.info("Found total pages", total_pages=total_pages)
    
    # Generate URLs for all pages
    urls = []
    if total_pages == 1:
        urls = [search_url]
    else:
        urls = [f"{search_url}-pagina-{i}.html" for i in range(1, total_pages + 1)]
    
    downloaded_files = []
    
    # Download each page
    for index, url in enumerate(tqdm(urls, desc="Downloading pages"), start=1):
        filename = os.path.join(folder_path, f'listings-{index:03}.html')
        
        if not os.path.exists(filename):
            try:
                logger.debug("Downloading page", page=index, url=url)
                # Add delay between requests
                if index > 1:  # Don't delay on first request
                    time.sleep(delay)
                res = scraper.get(url, timeout=30)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    with open(filename, 'w', encoding='utf-8') as file:
                        file.write(str(soup))
                    downloaded_files.append(filename)
                    logger.debug("Page downloaded successfully", file=filename)
                else:
                    logger.error("Failed to download page", page=index, status_code=res.status_code)
            except Exception as e:
                logger.error("Error downloading page", page=index, error=str(e))
        else:
            logger.debug("File already exists, skipping", file=filename)
            downloaded_files.append(filename)
    
    logger.info("Download completed", total_files=len(downloaded_files))
    return downloaded_files


def download_zonaprop_for_analyzer(search_url: str, output_dir: Optional[str] = None) -> str:
    """
    Convenience function to download Zonaprop pages for use with RealEstateAnalyzer.
    
    Args:
        search_url: Zonaprop search URL
        output_dir: Optional output directory (defaults to temp directory)
        
    Returns:
        Path to directory containing downloaded HTML files
    """
    if output_dir is None:
        # Create a temp directory based on the URL
        url_hash = abs(hash(search_url)) % 10000
        output_dir = f"temp_zonaprop_{url_hash}"
    
    try:
        downloaded_files = download_zonaprop_pages(search_url, output_dir, overwrite=True)
        logger.info("Downloaded files for analyzer", 
                   directory=output_dir, 
                   file_count=len(downloaded_files))
        return output_dir
    except Exception as e:
        logger.error("Failed to download Zonaprop pages", error=str(e))
        raise


if __name__ == "__main__":
    # Example usage
    search_url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios-50000-130000-dolar.html"
    folder_path = "raw_data/zonaprop"
    
    try:
        files = download_zonaprop_pages(search_url, folder_path, overwrite=True)
        print(f"Downloaded {len(files)} files to {folder_path}")
    except Exception as e:
        print(f"Download failed: {e}")