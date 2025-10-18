#!/usr/bin/env python3
"""
Integration test for ZonapropPlaywrightClient.

Tests the Playwright-based scraping approach end-to-end.
"""

import asyncio
import sys
from pathlib import Path

# Add renta to path
sys.path.insert(0, str(Path(__file__).parent))

from renta.config import ConfigManager
from renta.zonaprop_playwright_client import ZonapropPlaywrightClient
from renta.utils.async_scraper_wrapper import scrape_zonaprop_async


async def test_playwright_client():
    """Test ZonapropPlaywrightClient directly."""
    print("="*80)
    print("TEST 1: Direct ZonapropPlaywrightClient Test")
    print("="*80)

    # Create config
    config = ConfigManager()

    # Test search URL - 2 bedroom apartments in Buenos Aires
    search_url = "https://www.zonaprop.com.ar/departamentos-venta-capital-federal-2-dormitorios.html"

    print(f"\nSearch URL: {search_url}")
    print("Creating Playwright client...")

    try:
        async with ZonapropPlaywrightClient(config) as client:
            print("✓ Client created successfully")
            print("\nStarting scrape (max 2 pages for testing)...")

            df = await client.scrape_search_results(search_url, max_pages=2)

            print(f"\n✓ Scraping completed!")
            print(f"  - Total properties: {len(df)}")
            print(f"  - Columns: {list(df.columns)}")

            if len(df) > 0:
                print(f"\nFirst property sample:")
                print(df.iloc[0].to_dict())

                # Check for required columns
                required_cols = ['id', 'title', 'price_usd', 'latitude', 'longitude']
                missing_cols = [col for col in required_cols if col not in df.columns]

                if missing_cols:
                    print(f"\n⚠ Missing columns: {missing_cols}")
                else:
                    print(f"\n✓ All required columns present")

                # Check data quality
                has_coords = df['latitude'].notna().sum()
                has_price = df['price_usd'].notna().sum()
                print(f"\nData quality:")
                print(f"  - Properties with coordinates: {has_coords}/{len(df)} ({100*has_coords/len(df):.1f}%)")
                print(f"  - Properties with USD price: {has_price}/{len(df)} ({100*has_price/len(df):.1f}%)")

                return True
            else:
                print("\n✗ No properties found")
                return False

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_async_wrapper():
    """Test the async wrapper function."""
    print("\n" + "="*80)
    print("TEST 2: Async Wrapper Test")
    print("="*80)

    # Create config with Playwright enabled
    config = ConfigManager()

    # Temporarily enable Playwright
    original_value = config.get("zonaprop.scraping.use_playwright", False)
    config.set("zonaprop.scraping.use_playwright", True)

    search_url = "https://www.zonaprop.com.ar/departamentos-venta-palermo-2-dormitorios.html"

    print(f"\nSearch URL: {search_url}")
    print("Using async wrapper (should use Playwright)...")

    try:
        df = await scrape_zonaprop_async(search_url, config, max_pages=1)

        print(f"\n✓ Async wrapper completed!")
        print(f"  - Total properties: {len(df)}")

        if len(df) > 0:
            print(f"  - Sample title: {df.iloc[0]['title']}")
            return True
        else:
            print("\n⚠ No properties found")
            return False

    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Restore original config value
        config.set("zonaprop.scraping.use_playwright", original_value)


async def main():
    """Run all tests."""
    print("\n" + "🎭" * 20)
    print(" ZONAPROP PLAYWRIGHT INTEGRATION TESTS")
    print("🎭" * 20 + "\n")

    results = []

    # Test 1: Direct client usage
    test1_passed = await test_playwright_client()
    results.append(("Direct Client Test", test1_passed))

    # Test 2: Async wrapper
    test2_passed = await test_async_wrapper()
    results.append(("Async Wrapper Test", test2_passed))

    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name}: {status}")

    all_passed = all(passed for _, passed in results)

    print("\n" + "="*80)
    if all_passed:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*80 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
