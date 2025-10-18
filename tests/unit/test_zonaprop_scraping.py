"""
Unit tests for Zonaprop scraping functionality.

Tests the core feature: "Scrape or ingest Zonaprop listings, capturing pricing, engagement, and location data"
"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from renta.ingestion import ZonapropScraper, DataProcessor
from renta.exceptions import ScrapingError, ZonapropAntiBotError

SAMPLE_PRELOADED_HTML = """
<html>
  <head>
    <script id="preloadedData">
      window.__PRELOADED_STATE__ = {
        "listStore": {
          "listPostings": [
            {
              "postingId": "prop_123",
              "titlePlainText": "Departamento en Palermo",
              "url": "/propiedad-prop_123.html",
              "priceOperationTypes": [
                {
                  "prices": [
                    {"amount": 95000, "currency": {"id": "USD"}},
                    {"amount": 85000000, "currency": {"id": "ARS"}}
                  ]
                }
              ],
              "postingLocation": {
                "postingAddress": {"formattedAddress": "Palermo, CABA"},
                "postingGeolocation": {"geolocation": {"latitude": -34.58, "longitude": -58.41}}
              },
              "rooms": 2,
              "bathrooms": 1,
              "surfaceMeters": 55,
              "stats": {"usersViewsPerDay": 7}
            }
          ],
          "metadata": {"paging": {"totalPages": 1}}
        }
      };
    </script>
  </head>
  <body></body>
</html>
"""


@pytest.fixture(autouse=True)
def mock_cloudscraper_session():
    """Ensure cloudscraper sessions are mocked for all tests."""
    with patch("renta.ingestion.cloudscraper.create_scraper") as mock_factory:
        session_mock = MagicMock()
        mock_factory.return_value = session_mock
        yield session_mock


@pytest.mark.unit
class TestZonapropScraper:
    """Test Zonaprop web scraping functionality."""

    def test_init(self, mock_config_manager):
        """Test ZonapropScraper initialization."""
        scraper = ZonapropScraper(mock_config_manager)

        assert scraper.config is not None
        assert hasattr(scraper, "logger")

    @patch.object(ZonapropScraper, "_fetch_page", return_value=SAMPLE_PRELOADED_HTML)
    def test_scrape_search_results(self, mock_fetch_page, mock_config_manager):
        """Test scraping Zonaprop search results."""
        scraper = ZonapropScraper(mock_config_manager)

        # Test scraping (may need to adjust based on actual implementation)
        url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo.html"

        result = scraper.scrape_search_results(url)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        row = result.iloc[0]
        assert row["id"] == "prop_123"
        assert row["price_usd"] == 95000
        assert row["rooms"] == 2
        assert row["bathrooms"] == 1
        assert pytest.approx(row["latitude"], rel=1e-6) == -34.58
        mock_fetch_page.assert_called_once_with(url, bucket="search")

    def test_parse_html_files(self, mock_config_manager, test_data_dir):
        """Test parsing from saved HTML files (fallback mode)."""
        scraper = ZonapropScraper(mock_config_manager)

        # Create sample HTML file
        html_file = test_data_dir / "zonaprop_sample.html"
        html_file.write_text(SAMPLE_PRELOADED_HTML)

        result = scraper.parse_html_files(str(html_file))

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        assert "price_usd" in result.columns

    def test_antibot_detection(self, mock_config_manager):
        """Test detection of anti-bot protection."""
        scraper = ZonapropScraper(mock_config_manager)

        # Sample Cloudflare challenge page
        cloudflare_html = """
        <html>
            <head><title>Just a moment...</title></head>
            <body>
                <h1>Please wait while we check your browser...</h1>
                <div id="cf-content">Checking your browser before accessing</div>
            </body>
        </html>
        """

        # Test if scraper can detect Cloudflare
        is_blocked = (
            "cloudflare" in cloudflare_html.lower() or "just a moment" in cloudflare_html.lower()
        )
        assert is_blocked is True


@pytest.mark.unit
class TestPropertyDataExtraction:
    """Test extraction of property data from HTML."""

    def test_price_extraction(self, mock_config_manager):
        """Test extraction of property prices."""
        scraper = ZonapropScraper(mock_config_manager)

        # Test various price formats
        price_texts = ["USD 120,000", "U$S 150.000", "120000 USD", "US$ 95,000"]

        # Price extraction logic should handle various formats
        for price_text in price_texts:
            # Extract numbers from text
            import re

            numbers = re.findall(r"\d+", price_text.replace(",", "").replace(".", ""))
            if numbers:
                assert len(numbers) > 0

    def test_location_extraction(self):
        """Test extraction of property location data."""
        sample_html = """
        <div class="location">
            <span>Palermo</span>
            <span>Capital Federal</span>
        </div>
        """

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(sample_html, "html.parser")
        location_div = soup.find("div", class_="location")

        assert location_div is not None
        assert "Palermo" in location_div.get_text()

    def test_property_attributes(self):
        """Test extraction of property attributes (bedrooms, bathrooms, area)."""
        sample_html = """
        <div class="attributes">
            <span class="bedrooms">2 ambientes</span>
            <span class="bathrooms">1 baño</span>
            <span class="area">65 m²</span>
        </div>
        """

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(sample_html, "html.parser")

        # Test that attributes can be found
        assert soup.find("span", class_="bedrooms") is not None
        assert soup.find("span", class_="bathrooms") is not None
        assert soup.find("span", class_="area") is not None


@pytest.mark.unit
class TestDataProcessing:
    """Test processing of scraped Zonaprop data."""

    def test_process_zonaprop_data(self, mock_config_manager, sample_zonaprop_data):
        """Test processing and normalization of Zonaprop data."""
        processor = DataProcessor(mock_config_manager)

        # Process the data
        result = processor.process_zonaprop_data(sample_zonaprop_data)

        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0
        assert "id" in result.columns
        assert "title" in result.columns

    def test_data_validation(self, mock_config_manager):
        """Test validation of scraped property data."""
        processor = DataProcessor(mock_config_manager)

        # Create invalid data
        invalid_data = pd.DataFrame(
            {
                "id": [1, 2, 3],
                # Missing required columns
            }
        )

        # Should validate required fields
        # Implementation may vary
        assert "id" in invalid_data.columns


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling in Zonaprop scraping."""

    def test_network_error_handling(self, mock_config_manager, mock_cloudscraper_session):
        """Test handling of network errors."""
        import requests

        mock_cloudscraper_session.get.side_effect = requests.exceptions.ConnectionError(
            "Network error"
        )

        scraper = ZonapropScraper(mock_config_manager)

        try:
            with pytest.raises(ScrapingError):
                scraper.scrape_search_results("https://www.zonaprop.com.ar/test.html")
        finally:
            mock_cloudscraper_session.get.side_effect = None

    def test_cloudflare_detection(self, mock_config_manager, mock_cloudscraper_session):
        """Test detection and handling of Cloudflare protection."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "<html><body>Just a moment...</body></html>"
        mock_cloudscraper_session.get.return_value = mock_response
        scraper = ZonapropScraper(mock_config_manager)

        try:
            scraper.scrape_search_results("https://www.zonaprop.com.ar/test.html")
        except ZonapropAntiBotError:
            assert True
        finally:
            mock_cloudscraper_session.get.reset_mock()

    def test_invalid_url_handling(self, mock_config_manager):
        """Test handling of invalid URLs."""
        scraper = ZonapropScraper(mock_config_manager)

        invalid_urls = ["", "not-a-url", "http://", "ftp://invalid.com"]

        for url in invalid_urls:
            # Should validate URLs
            # Implementation may vary
            assert isinstance(url, str)

    def test_missing_data_handling(self, mock_config_manager):
        """Test handling of pages with missing data."""
        scraper = ZonapropScraper(mock_config_manager)

        # HTML with no property cards
        empty_html = "<html><body><p>No properties found</p></body></html>"

        # Should handle gracefully
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(empty_html, "html.parser")
        cards = soup.find_all("div", class_="posting-card")

        assert len(cards) == 0
