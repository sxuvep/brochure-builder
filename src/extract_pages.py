import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


def fetch_html(url: str, retries: int = 2) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < retries:
                wait_time = (2 ** attempt)
                print(f"Retry {attempt + 1}/{retries} for {url} after {wait_time}s...")
                time.sleep(wait_time)
    raise last_error

def extract_text(html:str) -> tuple[str,str]:
    soup = BeautifulSoup(html,"lxml")

    # remove script and style elements which are not useful for brochure content
    for tag in soup(["script","style", "noscript"]):
        tag.decompose()

    title = soup.title.get_text("", strip = True) if soup.title else ""

    main = soup.find("main") or soup.find("article") or soup.body

    blocks = []
    for el in main.find_all(["h1","h2","h3","p","li"]):
        text = el.get_text(" ", strip=True)
        if text and len(text) > 25: # filter out very short text which is unlikely to be useful for brochure content:
            blocks.append(text)
    # join the blocks with newlines to create a single string of content which is easier to work with for the LLM and also preserves some structure with the newlines. We can also consider other delimiters like double newlines or special tokens if needed.
    content = "\n".join(blocks)
    content = re.sub(r"\n{3,}", "\n\n", content).strip() # replace multiple newlines with double newlines to avoid very long gaps in the content
    return title, content

# this function helps prevent errors when saving files by converting URLs into safe filenames. It extracts the path from the URL and replaces any characters that are not letters, numbers, underscores, or hyphens with underscores. If the path is empty (like for the homepage), it uses "home" as the filename. This way we can save the extracted content into files without worrying about invalid characters in filenames.
def safe_filename(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        path = "home"
    return re.sub(r"[^a-zA-Z0-9_-]", "_", path)

def extract_pages_from_links(links: list[dict], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written_files = []
    errors = []

    def process_link(i: int, item: dict) -> tuple:
        url = item.get("url")
        page_type = item.get("type", "unknown")
        if not url:
            return None

        try:
            html = fetch_html(url)
            title, text = extract_text(html)

            page_data = {
                "type": page_type,
                "url": url,
                "title": title,
                "text": text[:15000],
            }

            filename = f"{i:02d}_{page_type}_{safe_filename(url)}.json"
            output_path = output_dir / filename
            output_path.write_text(json.dumps(page_data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"✓ Saved {filename} (chars = {len(text)})")
            return output_path
        except Exception as e:
            error_msg = f"Error processing {url}: {e}"
            print(error_msg)
            errors.append(error_msg)
            return None

    # Use ThreadPoolExecutor for parallel extraction (up to 5 concurrent)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_link, i, item): i for i, item in enumerate(links, start=1)}
        for future in as_completed(futures):
            result = future.result()
            if result:
                written_files.append(result)

    if errors and not written_files:
        raise RuntimeError(f"Failed to extract any pages. Details:\n" + "\n".join(errors[:3]))

    return written_files

def main():
    input_file = Path("outputs/final_urls.json")
    output_dir = Path("outputs/pages")
    output_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(input_file.read_text(encoding="utf-8"))
    links = data.get("links", [])

    print(f"Extracting content from {len(links)} pages...\n")

    extract_pages_from_links(links, output_dir)

if __name__ == "__main__":
    main()
