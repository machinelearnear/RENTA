#!/usr/bin/env python3
"""
Cloudflare authentication helper for Zonaprop.

This module helps bypass Cloudflare protection by:
1. Opening a browser window for manual CAPTCHA solving
2. Saving valid cookies for reuse
3. Providing cookie management for Playwright sessions
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import Stealth
import structlog

from ..config import ConfigManager

logger = structlog.get_logger(__name__)


class CloudflareAuthManager:
    """
    Manages Cloudflare authentication via manual CAPTCHA solving and cookie persistence.

    This class helps bypass Cloudflare protection by:
    - Opening a browser for the user to manually solve CAPTCHA
    - Saving valid cookies to a local file
    - Providing cookie loading for automated sessions
    - Detecting when cookies expire and prompting re-authentication
    """

    def __init__(self, config: Optional[ConfigManager] = None):
        """
        Initialize the authentication manager.

        Args:
            config: Optional ConfigManager instance. If not provided, uses default config.
        """
        self.config = config or ConfigManager()

        # Cookie storage location
        self.cookie_file = Path.home() / ".renta" / "zonaprop_cookies.json"
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)

        # Playwright configuration
        self.headless = False  # Always visible for manual CAPTCHA solving
        self.viewport = self.config.get("zonaprop.playwright.viewport", {"width": 1920, "height": 1080})
        self.user_agent = self.config.get(
            "zonaprop.playwright.user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        self.locale = self.config.get("zonaprop.playwright.locale", "es-AR")
        self.timezone = self.config.get("zonaprop.playwright.timezone", "America/Argentina/Buenos_Aires")

    def has_valid_cookies(self) -> bool:
        """
        Check if valid cookies exist and are not expired.

        Returns:
            True if valid cookies exist, False otherwise
        """
        if not self.cookie_file.exists():
            return False

        try:
            with open(self.cookie_file, 'r') as f:
                data = json.load(f)

            cookies = data.get('cookies', [])
            timestamp = data.get('timestamp', 0)

            if not cookies:
                return False

            # Check if cookies are less than 24 hours old
            age_hours = (time.time() - timestamp) / 3600
            if age_hours > 24:
                logger.info("Cookies expired (older than 24 hours)", age_hours=age_hours)
                return False

            logger.info("Valid cookies found", age_hours=age_hours, cookie_count=len(cookies))
            return True

        except Exception as e:
            logger.warning("Failed to read cookie file", error=str(e))
            return False

    def load_cookies(self) -> List[Dict]:
        """
        Load cookies from the cookie file.

        Returns:
            List of cookie dictionaries

        Raises:
            FileNotFoundError: If cookie file doesn't exist
        """
        if not self.cookie_file.exists():
            raise FileNotFoundError(f"Cookie file not found: {self.cookie_file}")

        with open(self.cookie_file, 'r') as f:
            data = json.load(f)

        return data.get('cookies', [])

    def save_cookies(self, cookies: List[Dict]) -> None:
        """
        Save cookies to the cookie file.

        Args:
            cookies: List of cookie dictionaries from Playwright
        """
        data = {
            'cookies': cookies,
            'timestamp': time.time(),
            'domain': 'zonaprop.com.ar'
        }

        with open(self.cookie_file, 'w') as f:
            json.dump(data, f, indent=2)

        logger.info("Cookies saved", cookie_count=len(cookies), file=str(self.cookie_file))

    async def authenticate_manual(self, url: str = "https://www.zonaprop.com.ar") -> None:
        """
        Open a browser for manual Cloudflare CAPTCHA solving and save cookies.

        This method:
        1. Opens a visible browser window
        2. Navigates to Zonaprop
        3. Waits for the user to solve Cloudflare challenge
        4. Saves valid cookies for future use

        Args:
            url: URL to navigate to (default: Zonaprop homepage)
        """
        logger.info("Opening browser for manual Cloudflare authentication")
        print("\n" + "="*80)
        print("CLOUDFLARE AUTHENTICATION")
        print("="*80)
        print(f"\nA browser window will open to: {url}")
        print("\nPlease complete the following steps:")
        print("  1. Wait for the Cloudflare challenge page to appear")
        print("  2. Complete the CAPTCHA/verification if prompted")
        print("  3. Wait until the page fully loads (you should see property listings)")
        print("  4. Press Enter in this terminal when ready")
        print("\nThe browser window will remain open for 2 minutes.")
        print("="*80 + "\n")

        async with async_playwright() as p:
            # Launch browser
            browser: Browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )

            # Create context with realistic settings
            context: BrowserContext = await browser.new_context(
                viewport=self.viewport,
                user_agent=self.user_agent,
                locale=self.locale,
                timezone_id=self.timezone,
                color_scheme='light',
                device_scale_factor=1,
                has_touch=False,
                is_mobile=False
            )

            # Create page and apply stealth
            page: Page = await context.new_page()
            stealth = Stealth()
            await stealth.apply_stealth_async(page)

            # Navigate to URL
            logger.info("Navigating to Zonaprop", url=url)
            await page.goto(url, wait_until='domcontentloaded')

            # Wait for user to solve CAPTCHA
            print("\n⏳ Waiting for you to solve the Cloudflare challenge...")
            print("   (The browser will auto-close after 2 minutes or press Ctrl+C to close manually)\n")

            try:
                # Wait up to 2 minutes for user interaction
                await asyncio.sleep(120)
            except KeyboardInterrupt:
                print("\n✓ User interaction complete")

            # Get cookies
            cookies = await context.cookies()

            # Filter for zonaprop.com.ar domain
            zonaprop_cookies = [c for c in cookies if 'zonaprop.com.ar' in c.get('domain', '')]

            if zonaprop_cookies:
                self.save_cookies(zonaprop_cookies)
                print(f"\n✅ SUCCESS! Saved {len(zonaprop_cookies)} cookies")
                print(f"   Cookie file: {self.cookie_file}")
                print("\nYou can now use Playwright scraping with these cookies.\n")
            else:
                print("\n⚠ WARNING: No zonaprop.com.ar cookies found")
                print("   Make sure the Cloudflare challenge was completed successfully.\n")

            # Close browser
            await browser.close()

    async def apply_cookies_to_context(self, context: BrowserContext) -> None:
        """
        Apply saved cookies to a Playwright browser context.

        Args:
            context: Playwright BrowserContext to add cookies to

        Raises:
            FileNotFoundError: If no cookies are saved
        """
        cookies = self.load_cookies()
        await context.add_cookies(cookies)
        logger.info("Applied cookies to browser context", cookie_count=len(cookies))

    def clear_cookies(self) -> None:
        """Delete the saved cookie file."""
        if self.cookie_file.exists():
            self.cookie_file.unlink()
            logger.info("Cookies cleared", file=str(self.cookie_file))
            print(f"✓ Cookies cleared from {self.cookie_file}")
        else:
            print("No cookies to clear")


async def main():
    """CLI tool for managing Cloudflare authentication."""
    import sys

    manager = CloudflareAuthManager()

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == 'auth':
            # Perform manual authentication
            url = sys.argv[2] if len(sys.argv) > 2 else "https://www.zonaprop.com.ar"
            await manager.authenticate_manual(url)

        elif command == 'check':
            # Check cookie status
            if manager.has_valid_cookies():
                cookies = manager.load_cookies()
                print(f"✓ Valid cookies found ({len(cookies)} cookies)")
                with open(manager.cookie_file, 'r') as f:
                    data = json.load(f)
                age_hours = (time.time() - data['timestamp']) / 3600
                print(f"  Age: {age_hours:.1f} hours")
                print(f"  File: {manager.cookie_file}")
            else:
                print("✗ No valid cookies found")
                print(f"  Run: python -m renta.utils.cloudflare_auth auth")

        elif command == 'clear':
            # Clear cookies
            manager.clear_cookies()

        else:
            print(f"Unknown command: {command}")
            print("\nUsage:")
            print("  python -m renta.utils.cloudflare_auth auth [url]  - Authenticate manually")
            print("  python -m renta.utils.cloudflare_auth check       - Check cookie status")
            print("  python -m renta.utils.cloudflare_auth clear       - Clear saved cookies")

    else:
        print("Cloudflare Authentication Manager for Zonaprop")
        print("\nUsage:")
        print("  python -m renta.utils.cloudflare_auth auth [url]  - Authenticate manually")
        print("  python -m renta.utils.cloudflare_auth check       - Check cookie status")
        print("  python -m renta.utils.cloudflare_auth clear       - Clear saved cookies")
        print("\nExample:")
        print("  python -m renta.utils.cloudflare_auth auth")


if __name__ == "__main__":
    asyncio.run(main())
