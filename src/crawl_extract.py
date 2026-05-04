# download the homepage HTML
# Parse the HTML
# Find all links
# Convert them into full URLs
# Keep only internal links (same website domain)
# Return the list
import json
from pathlib import Path
import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

def get_homepage_links(base_url):
    print(f"Fetching homepage: {base_url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    retries = 2
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(base_url, headers=headers, timeout=30)
            response.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < retries:
                wait_time = (2 ** attempt)
                print(f"Retry {attempt + 1}/{retries} after {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise last_error

    soup = BeautifulSoup(response.text,"lxml") # use lxml parser for better performance and handle messy HTML which is less strict than html.parser

    links = set()  # use a set to avoid duplicates
    for a in soup.find_all("a",href=True):
        full_url = urljoin(base_url,a["href"])

        # only keep internal links
        if urlparse(full_url).netloc == urlparse(base_url).netloc:
            links.add(full_url)

    print(f"Found {len(links)} internal links on the homepage.")
    return list(links)

def save_candidate_urls(base_url: str, output_path: Path) -> list[str]:
    urls = get_homepage_links(base_url)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(urls, ensure_ascii=False, indent=2), encoding="utf-8")
    return urls

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_urls.py <base_url>")
        sys.exit(1)

    base_url = sys.argv[1]
    output_path = Path("outputs/candidate_urls.json")
    save_candidate_urls(base_url, output_path)

    print(f"Saved candidate URLs to {output_path}")

if __name__ == "__main__":
    main()