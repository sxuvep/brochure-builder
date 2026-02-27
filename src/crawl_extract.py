# download the homepage HTML
# Parse the HTML
# Find all links
# Convert them into full URLs
# Keep only internal links (same website domain)
# Return the list
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