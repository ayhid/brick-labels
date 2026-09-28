"""Web scraping logic for fetching LEGO part information."""

import time
import re
from pathlib import Path
from typing import Dict, Optional
import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

from . import config


class PartFetcher:
    """Handles fetching LEGO part information from BrickArchitect."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.last_request_time = 0

    def _rate_limit(self):
        """Ensure we don't exceed rate limits."""
        elapsed = time.time() - self.last_request_time
        if elapsed < config.REQUEST_DELAY:
            time.sleep(config.REQUEST_DELAY - elapsed)
        self.last_request_time = time.time()

    def _log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"  {message}")

    def fetch_part_info(self, reference: str) -> Optional[Dict[str, str]]:
        """
        Fetch part information from BrickArchitect.

        Args:
            reference: LEGO part reference number

        Returns:
            Dict with 'title', 'reference', 'image_path' keys, or None if failed
        """
        self._rate_limit()

        url = config.BRICKARCHITECT_PART_URL.format(reference=reference)
        self._log(f"Fetching info for part {reference}...")

        try:
            response = self.session.get(url, timeout=10)

            if response.status_code == 404:
                print(f"Warning: Part {reference} not found (404)")
                return None

            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract title from page title
            title_tag = soup.find('title')
            if not title_tag:
                print(f"Warning: Could not find title for part {reference}")
                return None

            # Clean up title
            title = title_tag.text.strip()
            # Remove "(Part XXXX)" suffix
            title = re.sub(r'\s*\(Part\s+\d+\)\s*', '', title)
            # Remove " | BrickArchitect"
            title = title.replace(' | BrickArchitect', '').strip()
            # Remove " - LEGO Parts Guide - Brick Architect"
            title = re.sub(r'\s*-\s*LEGO Parts Guide\s*-\s*Brick Architect\s*$', '', title, flags=re.IGNORECASE)
            # Remove leading part reference like "3037 - "
            title = re.sub(r'^\d+\s*-\s*', '', title)

            if not title:
                title = f"LEGO Part {reference}"

            self._log(f"Found: {title}")

            # Download image
            image_path = self.download_image(reference)

            return {
                'title': title,
                'reference': reference,
                'image_path': image_path
            }

        except requests.RequestException as e:
            print(f"Error fetching part {reference}: {e}")
            # Retry once
            self._log("Retrying...")
            time.sleep(1)
            try:
                response = self.session.get(url, timeout=10)
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.text.strip()
                    title = re.sub(r'\s*\(Part\s+\d+\)\s*', '', title)
                    title = title.replace(' | BrickArchitect', '').strip()
                    image_path = self.download_image(reference)
                    return {
                        'title': title,
                        'reference': reference,
                        'image_path': image_path
                    }
            except Exception:
                pass

            return None

    def download_image(self, reference: str) -> Optional[str]:
        """
        Download part image from BrickArchitect.

        Args:
            reference: LEGO part reference number

        Returns:
            Path to cached image file, or None if failed
        """
        cache_path = config.CACHE_DIR / f"{reference}.png"

        # Return cached image if exists
        if cache_path.exists():
            self._log(f"Using cached image for {reference}")
            return str(cache_path)

        self._rate_limit()

        url = config.BRICKARCHITECT_IMAGE_URL.format(reference=reference)
        self._log(f"Downloading image for part {reference}...")

        try:
            response = self.session.get(url, timeout=10)

            if response.status_code == 404:
                self._log(f"Image not found for part {reference}")
                return None

            response.raise_for_status()

            # Verify it's a valid image
            try:
                img = Image.open(BytesIO(response.content))
                img.verify()

                # Save to cache
                with open(cache_path, 'wb') as f:
                    f.write(response.content)

                self._log(f"Image cached: {cache_path}")
                return str(cache_path)

            except Exception as e:
                self._log(f"Invalid image for part {reference}: {e}")
                return None

        except requests.RequestException as e:
            self._log(f"Error downloading image for {reference}: {e}")
            return None

    def fetch_multiple_parts(self, references: list) -> list:
        """
        Fetch information for multiple parts.

        Args:
            references: List of LEGO part reference numbers

        Returns:
            List of part info dicts (only successful fetches)
        """
        parts_data = []

        for ref in references:
            # Clean reference (remove whitespace, comments)
            ref = ref.strip()
            if not ref or ref.startswith('#'):
                continue

            info = self.fetch_part_info(ref)
            if info:
                parts_data.append(info)

        return parts_data
