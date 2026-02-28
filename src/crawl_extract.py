# download the homepage HTML
# Parse the HTML
# Find all links
# Convert them into full URLs
# Keep only internal links (same website domain)
# Return the list
import json
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

def get_homepage_links(base_url):
    print(f"Fetching homepage: {base_url}")

    response = requests.get(base_url,timeout=30)
    # Raise an error for HTTP errors
    # so we are stopped if the homepage is not accessible
    response.raise_for_status()

    soup = BeautifulSoup(response.text,"lxml") # use lxml parser for better performance and handle messy HTML which is less strict than html.parser

    links = set()  # use a set to avoid duplicates
    for a in soup.find_all("a",href=True):
        full_url = urljoin(base_url,a["href"])

        # only keep internal links
        if urlparse(full_url).netloc == urlparse(base_url).netloc:
            links.add(full_url)

    print(f"Found {len(links)} internal links on the homepage.")
    return list(links)

def main():
    base_url = "https://radetco.com/"
    urls = get_homepage_links(base_url)

    # Save the URLs to a file for the next step
    output_path = Path("outputs/candidate_urls.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(json.dumps(urls, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved candidate URLs to {output_path}")

if __name__ == "__main__":
    main()