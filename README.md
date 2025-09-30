# Encontrá Tu Casa - Backend

Backend scripts for real estate investment analysis in Buenos Aires, Argentina. This tool scrapes property listings from Zonaprop, enriches them with Airbnb rental data, and uses LLMs to generate investment summaries in Spanish.

## 🏠 What It Does

1. **Downloads Airbnb Data**: Fetches historical rental data from InsideAirbnb for Buenos Aires
2. **Scrapes Zonaprop**: Extracts property listings with prices, features, and user engagement metrics
3. **Enriches with Context**: Matches properties with nearby Airbnb listings to estimate rental potential
4. **LLM Analysis**: Generates investment summaries in Argentinian Spanish using AI

## 📊 Output Example

For each high-interest property (>60 views/day), you get:
- Asking price in USD and price per m²
- Monthly expenses (expensas)
- Nearby Airbnb rental prices and occupancy estimates
- AI-generated investment summary in Spanish
- Direct links to listing, Google Maps, and WhatsApp contact

## 🚀 Quick Start

### Prerequisites

```bash
pip install pandas numpy scikit-learn beautifulsoup4 cloudscraper python-dotenv tqdm requests lxml html5lib
```

### Option 1: Local Execution (with LiteLLM)

```bash
# Install LiteLLM
pip install litellm

# Set up API key (example with Together.ai)
export TOGETHER_API_KEY="your_key_here"

# Run
python main.py
```

### Option 2: AWS Bedrock

```bash
# Install AWS SDK
pip install boto3

# Configure AWS credentials
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"
export AWS_REGION="us-east-1"

# Enable model access in AWS Console:
# Bedrock > Model access > Request access to Claude 3.5 Sonnet

# Run
python main_bedrock.py
```

## 🔧 Configuration

Edit the `SEARCH_URL` at the bottom of either script to customize your property search:

```python
# Example: 2-bedroom apartments in Palermo, $50k-$130k USD
SEARCH_URL = "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios-50000-130000-dolar.html"
```

Then configure the workflow:

```python
main(
    search_url=SEARCH_URL,
    download_airbnb=False,      # True on first run to download Airbnb data
    scrape_zonaprop=True,        # Scrape fresh Zonaprop listings
    analyze=True,                # Generate LLM summaries
    bedrock_model="anthropic.claude-3-5-sonnet-20241022-v2:0",  # AWS only
    aws_region='us-east-1'       # AWS only
)
```

## 📁 File Structure

```
encontra-tu-casa-backend/
├── main.py              # Local version (LiteLLM)
├── main_bedrock.py      # AWS Bedrock version
├── README.md
├── raw_data/            # Downloaded HTML and data (gitignored)
│   ├── airbnb/
│   └── zonaprop/
└── processed/           # Processed CSVs and analysis results (gitignored)
    └── analysis_results_YYYYMMDD_HHMMSS.csv
```

## 🤖 Supported LLM Models

### Local (main.py) - via LiteLLM
- Together.ai Mixtral-8x7B (~$0.60/M tokens)
- Anthropic Claude via API
- OpenAI GPT-4
- Any LiteLLM-supported provider

### AWS Bedrock (main_bedrock.py)
- `anthropic.claude-3-5-sonnet-20241022-v2:0` ⭐ Recommended
- `anthropic.claude-3-haiku-20240307-v1:0` (10x cheaper)
- `mistral.mistral-large-2402-v1:0`
- `meta.llama3-70b-instruct-v1:0`

## 💰 Cost Estimates

**For 100 property summaries:**

| Provider | Model | Cost |
|----------|-------|------|
| Together.ai | Mixtral-8x7B | ~$0.15 |
| AWS Bedrock | Claude 3 Haiku | ~$0.50 |
| AWS Bedrock | Claude 3.5 Sonnet | ~$3.00 |

## 🧠 How It Works

### Part 1: Airbnb Data Processing
1. Scrapes InsideAirbnb for Buenos Aires listings
2. Converts ARS prices to USD using historical exchange rates
3. Calculates occupancy estimates (high/medium/low) based on review frequency
4. Saves to `processed/airbnb_listings.csv`

### Part 2: Zonaprop Scraping
1. Takes a Zonaprop search URL with your filters
2. Uses cloudscraper to bypass anti-bot protection
3. Downloads all paginated results as HTML
4. Parses embedded JSON to extract property details
5. Revisits each listing to scrape user view counts
6. Calculates popularity metric: `views_per_day`
7. Saves to `processed/{search-name}/zonaprop_with_userviews.csv`

### Part 3: LLM Analysis
1. Filters properties by `views_per_day` (default: >60 = hot properties)
2. For each listing, finds nearby Airbnb listings within 300m radius
3. Calculates rental potential metrics:
   - Average Airbnb prices (entire home vs. private room)
   - Review scores (rating, location, value)
   - Occupancy probability (high/low)
4. Sends combined context to LLM with prompt in Spanish
5. LLM generates investment summary with Argentinian accent
6. Saves results to `processed/analysis_results_{timestamp}.csv`

## 🔑 Key Metrics Explained

- **views_per_day**: User engagement on Zonaprop (>60 = very hot)
- **usd_per_m2**: Price per square meter in USD
- **airbnb_probabilidad_alquiler**: Rental probability based on nearby occupancy
- **airbnb_avg_price_entire_home**: Average nightly rate for comparable Airbnbs

## 📝 Example Output

```csv
listing_url,asking_price_in_usd,views_per_day,usd_per_m2,summary
https://www.zonaprop.com...,95000,66,1938,"Che, esta propiedad en Palermo está a 95.000 dólares..."
```

## ⚠️ Rate Limits & Considerations

- **Zonaprop**: Uses cloudscraper with 30s delay to avoid blocks
- **LLM APIs**: Includes retry logic for failed requests
- **First Run**: Downloading Airbnb data + exchange rates takes ~15 minutes
- **Subsequent Runs**: Only scrapes Zonaprop (~5-10 minutes for 100 listings)

## 🛠️ Troubleshooting

**"No Airbnb data found"**
→ Run with `download_airbnb=True` on first execution

**"Error 403 from Zonaprop"**
→ Cloudscraper delay may need adjustment, or IP temporarily blocked

**"Bedrock model access denied"**
→ Go to AWS Console > Bedrock > Model access and request access

**"Exchange rate fetch failing"**
→ Check internet connection, xe.com may be rate limiting

## 🤝 Contributing

This is a personal project, but feel free to fork and adapt for your own market!

## 📄 License

MIT License - Use freely, no warranty provided

## 🙏 Credits

- Data: [InsideAirbnb](http://insideairbnb.com/)
- Inspired by [Santiago Magnin's real estate webinars](https://www.youtube.com/@santiagomagninoficial)
- Built with ❤️ for finding the perfect Buenos Aires apartment

---

**Disclaimer**: This tool is for research and educational purposes. Always verify property information directly with sellers and conduct proper due diligence before making investment decisions.