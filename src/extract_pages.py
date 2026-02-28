import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from pathlib import Path


def fetch_html(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()  # Raise an error for HTTP errors
    return response.text

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

def main():
    input_file = Path("outputs/final_urls.json")
    output_dir = Path("outputs/pages")
    output_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(input_file.read_text(encoding="utf-8"))
    links = data.get("links", [])

    print(f"Extracting content from {len(links)} pages...\n")

    for i, item in enumerate(links, start=1):
        url = item.get("url")
        page_type = item.get("type", "unknown")

        try:
            html = fetch_html(url)
            title,text = extract_text(html)

            page_data = {
                "type": page_type,
                "url":url,
                "title": title,
                "text": text[:15000] # limit text to 15000 characters to avoid very large files and also because LLMs have input limits so we want to keep it manageable for the next steps
            }

            filename = f"{i:02d}_{page_type}_{safe_filename(url)}.json"

            output_path = output_dir / filename

            output_path.write_text(json.dumps(page_data, ensure_ascii=False, indent=2), encoding="utf-8")

            print(f"Saved {filename} (chars = {len(text)})")

        except Exception as e:
            print(f"Error processing {url}: {e}")

if __name__ == "__main__":
    main()
