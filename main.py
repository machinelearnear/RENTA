#!/usr/bin/env python3
"""
End-to-end workflow for scraping Zonaprop listings and analyzing them with Airbnb data.
Combines the functionality from:
- 01-inside-airbnb-data.ipynb
- 02-scrape-zonaprop-listings.ipynb
- 03-load-data-and-run.ipynb
"""

import os
import re
import json
import string
import math
import shutil
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
import gzip
import numpy as np
import pandas as pd
import cloudscraper
from bs4 import BeautifulSoup
from tqdm import tqdm
from sklearn.neighbors import BallTree
from litellm import completion

# Load environment variables
load_dotenv()


# ============================================================================
# PART 1: Download and process InsideAirbnb data
# ============================================================================

def scrape_airbnb_buenos_aires_urls():
    """Scrape Airbnb Buenos Aires URLs from InsideAirbnb."""
    url = 'http://insideairbnb.com/get-the-data'
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    buenos_aires_section = soup.find('h3', string='Buenos Aires, Ciudad Autónoma de Buenos Aires, Argentina').find_next('table')

    urls = {}
    for row in buenos_aires_section.find_all('tr'):
        columns = row.find_all('td')
        if len(columns) > 1:
            file_name = columns[1].get_text(strip=True)
            file_url = columns[1].find('a')['href']
            urls[file_name] = file_url

    return urls


def download_and_uncompress_files(urls, data_dir='raw_data/airbnb'):
    """Download and uncompress Airbnb data files."""
    os.makedirs(data_dir, exist_ok=True)

    for file_name, url in tqdm(urls.items(), desc="Downloading Airbnb data"):
        local_filename = url.split('/')[-1]
        local_path = os.path.join(data_dir, local_filename)

        if os.path.exists(local_path):
            print(f"File {local_filename} already exists. Skipping download.")
            continue

        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

        print(f"Downloaded {file_name} to {local_path}")

        if local_filename.endswith('.gz'):
            uncompressed_filename = local_filename.replace('.csv.gz', '_full.csv')
            uncompressed_path = os.path.join(data_dir, uncompressed_filename)
            with gzip.open(local_path, 'rb') as f_in:
                with open(uncompressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            print(f"Uncompressed {local_filename} to {uncompressed_filename}")

            os.remove(local_path)
            print(f"Deleted compressed file {local_filename}")


def categorize_occupancy(reviews_l30d):
    """Categorize occupancy based on reviews in last 30 days."""
    estimated_nights = (reviews_l30d / 0.50) * 3
    if estimated_nights > 14:
        return 'high'
    elif estimated_nights >= 7:
        return 'medium'
    else:
        return 'low'


def process_airbnb_listings(data_dir='raw_data/airbnb'):
    """Process Airbnb listings data."""
    listings = pd.read_csv(f'{data_dir}/listings_full.csv')

    selected_columns = [
        'id', 'listing_url', 'last_scraped', 'neighbourhood_cleansed', 'latitude',
        'longitude', 'room_type', 'bathrooms_text', 'beds', 'price',
        'number_of_reviews_l30d', 'review_scores_rating', 'review_scores_location',
        'review_scores_value'
    ]

    filtered_listings = listings[selected_columns].reset_index(drop=True)

    # Add estimated nights booked
    filtered_listings['estimated_nights_booked_l30d'] = filtered_listings['number_of_reviews_l30d'].apply(categorize_occupancy)

    # Clean bathrooms_text
    filtered_listings['bathrooms'] = filtered_listings['bathrooms_text'].str.extract(r'(\d+\.?\d*)').astype(float)
    filtered_listings.drop(columns=['bathrooms_text'], inplace=True)

    # Get exchange rates
    filtered_listings['last_scraped'] = pd.to_datetime(filtered_listings['last_scraped'])
    start_date = filtered_listings['last_scraped'].min().date()
    end_date = filtered_listings['last_scraped'].max().date()

    ars_to_usd = pd.DataFrame()

    def daterange(start_date, end_date):
        for n in range(int((end_date - start_date).days)):
            yield start_date + timedelta(n)

    print("Fetching exchange rates...")
    for single_date in daterange(start_date, end_date):
        dfs = pd.read_html(f'https://www.xe.com/currencytables/?from=ARS&date={single_date.strftime("%Y-%m-%d")}')[0]
        dfs = dfs[dfs['Currency'] == 'USD']
        dfs['Date'] = single_date.strftime("%Y-%m-%d")
        ars_to_usd = pd.concat([ars_to_usd, dfs], ignore_index=True)

    # Convert dates
    filtered_listings['last_scraped'] = pd.to_datetime(filtered_listings['last_scraped']).dt.date
    ars_to_usd['Date'] = pd.to_datetime(ars_to_usd['Date']).dt.date

    # Clean price column
    filtered_listings['price'] = filtered_listings['price'].replace('[\$,]', '', regex=True).astype(float)

    # Calculate estimated price in USD
    estimated_prices_in_usd = []

    for row in tqdm(filtered_listings.itertuples(), total=len(filtered_listings), desc="Converting prices to USD"):
        exchange_rate = ars_to_usd[ars_to_usd['Date'] == getattr(row, 'last_scraped')]['ARS per unit']

        if not exchange_rate.empty and not pd.isna(row.price) and not pd.isna(exchange_rate.iloc[0]):
            estimated_price_usd = math.ceil(row.price / exchange_rate.iloc[0])
        else:
            estimated_price_usd = float('nan')

        estimated_prices_in_usd.append(estimated_price_usd)

    filtered_listings['estimated_price_per_night_in_USD'] = estimated_prices_in_usd

    return filtered_listings


def process_airbnb_reviews(data_dir='raw_data/airbnb'):
    """Process Airbnb reviews data."""
    reviews = pd.read_csv(f'{data_dir}/reviews_full.csv')
    reviews.drop(columns=['reviewer_id', 'reviewer_name'], inplace=True)
    return reviews


def save_airbnb_data(listings, reviews, output_dir='processed'):
    """Save processed Airbnb data."""
    os.makedirs(output_dir, exist_ok=True)
    listings.to_csv(f'{output_dir}/airbnb_listings.csv', index=False)
    reviews.to_csv(f'{output_dir}/airbnb_reviews.csv', index=False)
    print(f"Saved Airbnb data to {output_dir}/")


# ============================================================================
# PART 2: Scrape Zonaprop listings
# ============================================================================

def download_zonaprop_pages(search_url, folder_path='raw_data/zonaprop', overwrite=False):
    """Download Zonaprop search result pages."""
    scraper = cloudscraper.create_scraper(delay=30)

    os.makedirs(folder_path, exist_ok=True)

    if overwrite:
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            if os.path.isfile(file_path):
                os.unlink(file_path)
        print("Existing files deleted.")

    res = scraper.get(search_url)
    if res.status_code != 200:
        print(f'Error: {res.status_code}')
        return

    soup = BeautifulSoup(res.text, 'html.parser')

    total_pages = None
    for script in soup.find_all('script'):
        if 'totalPages' in script.text:
            match = re.search(r'"totalPages":(\d+)', script.text)
            if match:
                total_pages = int(match.group(1))
                break

    if not total_pages:
        print('Total pages not found.')
        return

    urls = [f"{search_url}-pagina-{i}.html" for i in range(1, total_pages + 1)]

    for index, url in enumerate(tqdm(urls, desc="Downloading Zonaprop pages"), start=1):
        filename = f'{folder_path}/listings-{index:03}.html'
        if not os.path.exists(filename):
            res = scraper.get(url)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                with open(filename, 'w', encoding='utf-8') as file:
                    file.write(str(soup))
            else:
                print(f'Error getting page {index}: {res.status_code}')
        else:
            print(f'File {filename} already exists, skipping download.')


def extract_property_data(soup):
    """Extract property data from HTML soup."""
    script = soup.find('script', id='preloadedData')

    if not script:
        return "No property data found."

    json_str = re.search(r'window\.__PRELOADED_STATE__ = (\{.*?\});', script.string, re.DOTALL | re.MULTILINE).group(1)
    data = json.loads(json_str)

    base_url = 'https://www.zonaprop.com.ar'

    extracted_data = []
    for prop in data['listStore']['listPostings']:
        amount_in_usd = prop['priceOperationTypes'][0]['prices'][0].get('amount', None)
        expenses_in_ars = prop['expenses']['amount'] if prop['expenses'] else None

        main_features = {feature_details['label'].lower().replace(' ', '_').translate(str.maketrans('', '', string.punctuation)): feature_details.get('value', 'No disponible')
                         for feature_id, feature_details in prop.get('mainFeatures', {}).items()}

        general_features = {feature_details['label'].lower().replace(' ', '_').translate(str.maketrans('', '', string.punctuation)): feature_details.get('value', 'No disponible')
                            for feature_id, feature_details in prop['generalFeatures'].get('Características generales', {}).items()}

        geolocation = prop['postingLocation']['postingGeolocation']['geolocation'] if prop['postingLocation']['postingGeolocation'] else {}
        latitude = geolocation.get('latitude', 'No latitude found')
        longitude = geolocation.get('longitude', 'No longitude found')

        visible_pictures = prop.get('visiblePictures')
        photos_urls = []
        if visible_pictures and isinstance(visible_pictures, dict):
            pictures = visible_pictures.get('pictures', [])
            if isinstance(pictures, list):
                photos_urls = [photo.get('url1200x1200') for photo in pictures if 'url1200x1200' in photo]

        google_maps = f"https://maps.google.com/?q={latitude},{longitude}"
        whatsapp = prop.get('whatsApp', '')
        modified_date = datetime.strptime(prop['modified_date'], "%Y-%m-%dT%H:%M:%S%z")

        extracted_data.append({
            "listing_url": base_url + prop.get('url', ''),
            "asking_price_in_usd": amount_in_usd,
            "expensas_in_ars": expenses_in_ars,
            "latitude": latitude,
            "longitude": longitude,
            "google_maps": google_maps,
            "photos": photos_urls,
            "whatsapp": re.sub(r'\s+', '', whatsapp) if whatsapp else '',
            "published_on": modified_date.strftime("%d-%m-%Y"),
            **main_features,
            **general_features,
        })

    return extracted_data


def create_dataframe_from_html(folder_path='raw_data/zonaprop'):
    """Create DataFrame from downloaded HTML files."""
    all_properties = []

    for filename in tqdm(os.listdir(folder_path), desc="Processing HTML files"):
        if filename.endswith('.html'):
            file_path = os.path.join(folder_path, filename)

            with open(file_path, 'r', encoding='utf-8') as file:
                soup = BeautifulSoup(file.read(), 'html.parser')

            properties_data = extract_property_data(soup)

            if isinstance(properties_data, list):
                all_properties.extend(properties_data)

    return pd.DataFrame(all_properties)


def extract_user_views(df):
    """Extract user views from each listing page."""
    scraper = cloudscraper.create_scraper(delay=30)
    resultados = []

    for url in tqdm(df['listing_url'], desc="Fetching user views"):
        res = scraper.get(url)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            script = soup.find('script', string=re.compile(r'usersViews\s*=\s*\d+|antiquity\s*=\s*\''))

            if script:
                match_users_views = re.search(r'usersViews\s*=\s*(\d+)', script.string)
                users_views = int(match_users_views.group(1)) if match_users_views else 0

                match_antiquity = re.search(r"antiquity\s*=\s*'Publicado hace (\d+) días'", script.string)
                if match_antiquity:
                    antiquity = int(match_antiquity.group(1))
                elif 'Publicado hoy' in script.string:
                    antiquity = 0
                elif 'Publicado desde ayer' in script.string:
                    antiquity = 1
                else:
                    antiquity = 0
            else:
                users_views = 0
                antiquity = 0

            if isinstance(users_views, int) and isinstance(antiquity, int) and antiquity != 0:
                views_per_day = users_views / antiquity
            else:
                views_per_day = 0

            resultados.append({
                'listing_url': url,
                'user_views': users_views,
                'days': antiquity,
                'views_per_day': int(views_per_day)
            })
        else:
            print(f'Error loading page: {res.status_code}')

    return pd.DataFrame(resultados)


def merge_and_recalculate(df_zonaprop, df_views):
    """Merge DataFrames and recalculate metrics."""
    df_merged = pd.merge(df_zonaprop, df_views, on='listing_url', how='left')

    hoy = datetime.now()

    for index, row in df_merged.iterrows():
        try:
            superficietotal = float(row['superficietotal'])
        except (ValueError, KeyError):
            superficietotal = None

        if superficietotal and superficietotal > 0:
            df_merged.at[index, 'usd_per_m2'] = int(row['asking_price_in_usd'] / superficietotal)
        else:
            df_merged.at[index, 'usd_per_m2'] = 0

        if row['user_views'] > 0 and row['days'] == 0:
            fecha_publicacion = datetime.strptime(row['published_on'], '%d-%m-%Y')
            diferencia_dias = (hoy - fecha_publicacion).days
            df_merged.at[index, 'days'] = diferencia_dias
        else:
            diferencia_dias = row['days']

        df_merged.at[index, 'views_per_day'] = int(row['user_views'] / min(diferencia_dias, 30)) if diferencia_dias > 0 else int(row['user_views'])

    return df_merged


def create_directory(search_url, output_dir='processed', delete=False):
    """Create directory based on search URL."""
    save_dir = search_url.split("/")[-1].replace(".html", "")
    folder_path = f'{output_dir}/{save_dir}'

    if os.path.exists(folder_path):
        if delete:
            shutil.rmtree(folder_path)
            print(f'Directory "{folder_path}" has been deleted.')
            os.makedirs(folder_path)
            print(f'New directory "{folder_path}" created.')
        else:
            print(f'Keeping existing directory "{folder_path}".')
    else:
        os.makedirs(folder_path)
        print(f'Directory "{folder_path}" created.')

    return folder_path


def save_zonaprop_data(zonaprop_df, folder_path):
    """Save Zonaprop data to CSV."""
    zonaprop_df.to_csv(f'{folder_path}/zonaprop_with_userviews.csv', index=False)
    print(f"Saved Zonaprop data to {folder_path}/")


# ============================================================================
# PART 3: Analysis with LLM
# ============================================================================

def find_within_radius(row, airbnb_listings, radius_km):
    """Find Airbnb listings within radius."""
    radius_rad = radius_km / 6371
    valid_listings = airbnb_listings.dropna(subset=['latitude', 'longitude'])
    tree = BallTree(np.deg2rad(valid_listings[['latitude', 'longitude']].values), metric='haversine')
    if pd.notnull(row['latitude']) and pd.notnull(row['longitude']):
        indices = tree.query_radius(np.deg2rad([[row['latitude'], row['longitude']]]), r=radius_rad)
        return valid_listings.iloc[indices[0]]
    return pd.DataFrame()


def add_airbnb_info(listings, airbnb_listings, radius_km):
    """Add Airbnb information to Zonaprop listings."""
    listings = listings.copy()
    listings['latitude'] = pd.to_numeric(listings['latitude'], errors='coerce')
    listings['longitude'] = pd.to_numeric(listings['longitude'], errors='coerce')

    for index, row in listings.iterrows():
        closest_listings = find_within_radius(row, airbnb_listings, radius_km)
        if closest_listings.empty:
            continue

        filtered = closest_listings.dropna(subset=['estimated_price_per_night_in_USD', 'review_scores_rating',
                                                   'review_scores_location', 'review_scores_value', 'room_type',
                                                   'estimated_nights_booked_l30d'])

        booking_counts = filtered['estimated_nights_booked_l30d'].value_counts()
        probabilidad_alquiler = 'más probable' if (booking_counts.get('high', 0) > booking_counts.get('low', 0)) or (
                booking_counts.get('high', 0) > booking_counts.get('medium', 0)) else 'menos probable'
        listings.at[index, 'airbnb_probabilidad_alquiler'] = probabilidad_alquiler

        listings.at[index, 'airbnb_avg_price_entire_home'] = int(
            filtered[filtered['room_type'] == 'Entire home/apt']['estimated_price_per_night_in_USD'].mean())
        listings.at[index, 'airbnb_avg_price_private_room'] = int(
            filtered[filtered['room_type'] == 'Private room']['estimated_price_per_night_in_USD'].mean())
        listings.at[index, 'airbnb_avg_review_score_rating'] = round(filtered['review_scores_rating'].mean(), 2)
        listings.at[index, 'airbnb_avg_review_score_location'] = round(filtered['review_scores_location'].mean(), 2)
        listings.at[index, 'airbnb_avg_review_score_value'] = round(filtered['review_scores_value'].mean(), 2)

    return listings


def info_del_listing(row):
    """Extract listing information for LLM prompt."""
    zonaprop = '\n'.join(f"- {col}: {row[col]}" for col in row.index if col not in
                         ['photos', 'listing_url', 'latitude', 'longitude', 'google_maps', 'whatsapp', 'days'] and
                         'airbnb_' not in col and pd.notnull(row[col]))
    airbnb = '\n'.join(f"- {col}: {row[col]}" for col in row.index if 'airbnb_' in col)
    return zonaprop, airbnb


def llm_response(row, model="together_ai/NousResearch/Nous-Hermes-2-Mixtral-8x7B-DPO"):
    """Get LLM response for listing summary."""
    system_instructions = """Always follow these instructions:
- Using the above context only, return a single paragraph summarizing all the information as your output.
- Write with strong Argentinian accent in Spanish.
- Be descriptive, don't skip words.
- For "Zonaprop", pay special attention to: 'asking_price_in_usd', 'expensas_in_ars', 'views_per_day', 'usd_per_m2'
- For "Airbnb", pay special attention to: 'average price', 'review score location', and `probabilidad de alquiler'. All prices are in USD.
- Be casual unless otherwise specified
- Be accurate, thorough, and descriptive
- No need to disclose you're an AI, nor greet me, or say goodbye.
"""

    info = info_del_listing(row)
    prompt = f"Return a dense summary from the given context:\n```Zonaprop:{info[0]}\n----\nAirbnb listings nearby:\n{info[1]}```"
    messages = [
        {"role": "system", "content": system_instructions},
        {"role": "user", "content": prompt},
    ]
    chat_completion = completion(
        messages=messages,
        model=model,
        max_tokens=1024
    )
    return chat_completion.choices[0].message.content


def analyze_listings(df, min_views=60, max_views=float('inf'), airbnb_listings=None, radius_km=0.3, show_top=10):
    """Analyze top listings based on views."""
    listings = df[(df.views_per_day > min_views) & (df.views_per_day <= max_views)].reset_index(drop=True)
    listings = listings.head(show_top)
    listings = add_airbnb_info(listings, airbnb_listings, radius_km)

    results = []
    for index, row in tqdm(listings.iterrows(), desc="Calling LLM API", total=len(listings)):
        summary = llm_response(row)
        results.append({
            'listing_url': row['listing_url'],
            'google_maps': row['google_maps'],
            'whatsapp': row['whatsapp'] if pd.notna(row['whatsapp']) else None,
            'summary': summary,
            'photos': row['photos']
        })

    return pd.DataFrame(results)


# ============================================================================
# MAIN WORKFLOW
# ============================================================================

def main(search_url, download_airbnb=False, scrape_zonaprop=True, analyze=True):
    """Main workflow."""
    print("=" * 80)
    print("ENCUENTRA TU CASA - End-to-End Workflow")
    print("=" * 80)

    # Step 1: Process Airbnb data (if needed)
    airbnb_listings = None
    if download_airbnb:
        print("\n[STEP 1] Downloading and processing Airbnb data...")
        urls = scrape_airbnb_buenos_aires_urls()
        download_and_uncompress_files(urls)
        airbnb_listings = process_airbnb_listings()
        airbnb_reviews = process_airbnb_reviews()
        save_airbnb_data(airbnb_listings, airbnb_reviews)
    else:
        print("\n[STEP 1] Loading existing Airbnb data...")
        if os.path.exists('processed/airbnb_listings.csv'):
            airbnb_listings = pd.read_csv('processed/airbnb_listings.csv')
            print(f"Loaded {len(airbnb_listings)} Airbnb listings")
        else:
            print("ERROR: Airbnb data not found. Run with download_airbnb=True first.")
            return

    # Step 2: Scrape Zonaprop
    zonaprop_listings = None
    if scrape_zonaprop:
        print(f"\n[STEP 2] Scraping Zonaprop listings from: {search_url}")
        download_zonaprop_pages(search_url, overwrite=True)
        zonaprop_listings = create_dataframe_from_html()
        print(f"Extracted {len(zonaprop_listings)} properties")

        print("\n[STEP 2b] Fetching user views data...")
        listings_user_views = extract_user_views(zonaprop_listings)
        zonaprop_listings = merge_and_recalculate(zonaprop_listings, listings_user_views)

        folder_path = create_directory(search_url, delete=True)
        save_zonaprop_data(zonaprop_listings, folder_path)
    else:
        print("\n[STEP 2] Skipping Zonaprop scraping...")
        # Load existing data
        folders = [f.path for f in os.scandir('processed') if f.is_dir()]
        if folders:
            latest_folder = max(folders, key=os.path.getmtime)
            csv_file = os.path.join(latest_folder, 'zonaprop_with_userviews.csv')
            if os.path.exists(csv_file):
                zonaprop_listings = pd.read_csv(csv_file)
                print(f"Loaded {len(zonaprop_listings)} Zonaprop listings from {csv_file}")
            else:
                print("ERROR: No Zonaprop data found.")
                return

    # Step 3: Analysis
    if analyze and zonaprop_listings is not None and airbnb_listings is not None:
        print("\n[STEP 3] Analyzing top listings...")
        results = analyze_listings(zonaprop_listings, min_views=60, airbnb_listings=airbnb_listings, show_top=10)

        output_file = f'processed/analysis_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        results.to_csv(output_file, index=False)
        print(f"\nAnalysis complete! Results saved to: {output_file}")
        print(f"Found {len(results)} high-interest properties")

    print("\n" + "=" * 80)
    print("Workflow complete!")
    print("=" * 80)


if __name__ == "__main__":
    # Example usage
    SEARCH_URL = "https://www.zonaprop.com.ar/inmuebles-venta-barrio-norte-palermo-colegiales-villa-crespo-publicado-hace-menos-de-45-dias-50000-130000-dolar-orden-visitas-descendente.html"

    # Run the workflow
    # Set download_airbnb=True on first run to download Airbnb data
    main(
        search_url=SEARCH_URL,
        download_airbnb=False,  # Set to True on first run
        scrape_zonaprop=True,
        analyze=True
    )