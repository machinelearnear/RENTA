"""
Manual download guide for Zonaprop when automated scraping fails.

This module provides instructions and utilities for manually downloading
Zonaprop HTML files when anti-bot protection prevents automated scraping.
"""

import structlog

logger = structlog.get_logger(__name__)


def print_manual_download_instructions(search_url: str, suggested_folder: str = "zonaprop_html") -> None:
    """
    Print detailed instructions for manually downloading Zonaprop HTML files.
    
    Args:
        search_url: The Zonaprop search URL that failed to scrape
        suggested_folder: Suggested folder name for saving HTML files
    """
    
    print("\n" + "="*80)
    print("🚫 ZONAPROP ANTI-BOT PROTECTION DETECTED")
    print("="*80)
    print("\nZonaprop has strong anti-bot protection that prevents automated scraping.")
    print("However, you can easily work around this by manually saving the HTML files.")
    print("\n📋 MANUAL DOWNLOAD INSTRUCTIONS:")
    print("-"*40)
    
    print(f"\n1. Open your web browser and go to:")
    print(f"   {search_url}")
    
    print(f"\n2. Create a folder for the HTML files:")
    print(f"   mkdir -p {suggested_folder}")
    
    print(f"\n3. For each page of results:")
    print(f"   • Right-click on the page → 'Save As' or 'Save Page As'")
    print(f"   • Save as HTML files in the {suggested_folder} folder")
    print(f"   • Name them: listings-001.html, listings-002.html, etc.")
    print(f"   • Navigate to next page and repeat")
    
    print(f"\n4. Once you have the HTML files, use them with RENTA:")
    print(f"   properties = analyzer.scrape_zonaprop(")
    print(f"       '{search_url}',")
    print(f"       html_path='{suggested_folder}'")
    print(f"   )")
    
    print("\n💡 ALTERNATIVE APPROACHES:")
    print("-"*30)
    print("• Use browser automation tools like Selenium")
    print("• Use a VPN or different IP address")
    print("• Try the search URL at different times of day")
    print("• Use a different browser or clear cookies/cache")
    
    print("\n📚 EXAMPLE CODE:")
    print("-"*20)
    print(f"""
# After manually downloading HTML files:
from renta import RealEstateAnalyzer

analyzer = RealEstateAnalyzer()

# Use the manually downloaded HTML files
properties = analyzer.scrape_zonaprop(
    '{search_url}',
    html_path='{suggested_folder}'
)

print(f"Loaded {{len(properties)}} properties from HTML files")
""")
    
    print("\n" + "="*80)


def create_sample_workflow_script(search_url: str, output_file: str = "manual_zonaprop_workflow.py") -> str:
    """
    Create a sample Python script showing the complete workflow with manual HTML files.
    
    Args:
        search_url: The Zonaprop search URL
        output_file: Name of the output Python script file
        
    Returns:
        Path to the created script file
    """
    
    script_content = f'''#!/usr/bin/env python3
"""
Sample workflow for using RENTA with manually downloaded Zonaprop HTML files.

This script demonstrates how to use RENTA when automated scraping fails
due to anti-bot protection.
"""

from renta import RealEstateAnalyzer
import os

def main():
    """Main workflow using manually downloaded HTML files."""
    
    # Initialize the analyzer
    analyzer = RealEstateAnalyzer()
    
    # Path to manually downloaded HTML files
    html_folder = "zonaprop_html"
    search_url = "{search_url}"
    
    # Check if HTML files exist
    if not os.path.exists(html_folder):
        print("❌ HTML folder not found!")
        print(f"Please create the folder '{{html_folder}}' and download HTML files manually.")
        print("See the manual download instructions for details.")
        return
    
    html_files = [f for f in os.listdir(html_folder) if f.endswith('.html')]
    if not html_files:
        print("❌ No HTML files found!")
        print(f"Please download HTML files to the '{{html_folder}}' folder.")
        return
    
    print(f"✓ Found {{len(html_files)}} HTML files in {{html_folder}}")
    
    try:
        # Step 1: Parse properties from HTML files
        print("\\n1. Parsing properties from HTML files...")
        properties = analyzer.scrape_zonaprop(search_url, html_path=html_folder)
        print(f"✓ Parsed {{len(properties)}} properties")
        
        # Step 2: Download Airbnb data
        print("\\n2. Downloading Airbnb data...")
        airbnb_data = analyzer.download_airbnb_data()
        print(f"✓ Downloaded {{len(airbnb_data)}} Airbnb listings")
        
        # Step 3: Enrich properties with Airbnb data
        print("\\n3. Enriching properties with Airbnb data...")
        enriched_properties = analyzer.enrich_with_airbnb(properties)
        print(f"✓ Enriched {{len(enriched_properties)}} properties")
        
        # Step 4: Generate AI summaries (optional)
        print("\\n4. Generating AI summaries...")
        try:
            summaries = analyzer.generate_summaries(enriched_properties)
            print(f"✓ Generated {{len(summaries)}} AI summaries")
        except Exception as e:
            print(f"⚠️  AI summaries failed: {{e}}")
            print("   (This is optional - you can still use the enriched data)")
        
        # Step 5: Export results
        print("\\n5. Exporting results...")
        output_file = "zonaprop_analysis_results.csv"
        analyzer.export(enriched_properties, format="csv", path=output_file)
        print(f"✓ Results exported to {{output_file}}")
        
        # Show summary
        print("\\n" + "="*60)
        print("📊 ANALYSIS COMPLETE!")
        print("="*60)
        print(f"Properties analyzed: {{len(enriched_properties)}}")
        print(f"Results saved to: {{output_file}}")
        
        # Show sample data
        if len(enriched_properties) > 0:
            print("\\nSample properties:")
            sample_cols = ['title', 'price_usd', 'surface_m2', 'match_status']
            available_cols = [col for col in sample_cols if col in enriched_properties.columns]
            if available_cols:
                print(enriched_properties[available_cols].head())
        
    except Exception as e:
        print(f"❌ Error during analysis: {{e}}")
        print("Please check your HTML files and try again.")

if __name__ == "__main__":
    main()
'''
    
    with open(output_file, 'w') as f:
        f.write(script_content)
    
    logger.info("Created sample workflow script", file=output_file)
    return output_file


if __name__ == "__main__":
    # Example usage
    search_url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios-50000-130000-dolar.html"
    print_manual_download_instructions(search_url)
    
    script_file = create_sample_workflow_script(search_url)
    print(f"\n📄 Sample workflow script created: {script_file}")