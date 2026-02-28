import json
from pathlib import Path
from urllib.parse import urlparse, urljoin, urldefrag

from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env (OPENAI_API_KEY=...)
load_dotenv()

client = OpenAI()

def clean_candidate_urls(urls, base_url):
    """
    Clean the list of candidate URLs BEFORE sending to OpenAI:
    - strip whitespace (fixes '.../training/ ')
    - remove #fragments (turns https://radetco.com/#faq into https://radetco.com/)
    - dedupe
    """
    cleaned = []
    seen = set()

    for u in urls:
        if not u:
            continue

        u = u.strip()
        u, _frag = urldefrag(u)  # removes #something

        if not u:
            continue

        if u not in seen:
            seen.add(u)
            cleaned.append(u)

    return cleaned


def pick_links_with_llm(base_url, urls):
    system_prompt = """
You are provided with a list of URLs found on a company website.
You decide which links are most relevant to include in a brochure about the company,
such as links to an About page, Products/Services/Solutions pages, Case Studies/Customers pages,
Careers/Jobs pages, Pricing (if available), and Contact page.

Rules:
- Only choose from the URLs provided (do not invent new URLs).
- Prefer internal links on the same domain.
- Avoid privacy policy, terms, blog/news category pages, and unrelated downloads unless needed.
- Pick at most 10 links.
- Return absolute URLs starting with https:// (no relative /about).
- Do not return URLs containing # fragments (like https://site.com/#faq).
- Return ONLY valid JSON (no extra text, no markdown).

Return JSON in this format:
{
  "links": [
    {"type": "about", "url": "https://full.url/about"},
    {"type": "products", "url": "https://full.url/solutions"},
    {"type": "careers", "url": "https://full.url/careers"},
    {"type": "contact", "url": "https://full.url/contact"}
  ]
}
""".strip()

    # Clean candidates before sending to OpenAI
    urls = clean_candidate_urls(urls, base_url)

    user_prompt = json.dumps(
        {
            "base_url": base_url,
            "urls": urls,
        },
        ensure_ascii=False,
    )

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    result_text = response.output_text.strip()

    try:
        data = json.loads(result_text)
    except json.JSONDecodeError:
        print("❌ Model did not return valid JSON. Raw output:\n")
        print(result_text)
        raise

    # Debug: show what model returned BEFORE filtering
    print("\nMODEL LINKS RAW (first 5):")
    print(data.get("links", [])[:5])

    # Post-filter: keep only same-domain links + fix relative URLs if any
    base_domain = urlparse(base_url).netloc.lower().removeprefix("www.")

    cleaned = []
    for item in data.get("links", []):
        u = (item.get("url") or "").strip()
        if not u:
            continue

        # Convert relative URLs to absolute
        full = urljoin(base_url, u)

        # Remove fragments just in case
        full, _frag = urldefrag(full)

        domain = urlparse(full).netloc.lower().removeprefix("www.")
        if domain == base_domain:
            item["url"] = full
            cleaned.append(item)

    data["links"] = cleaned

    # Debug: show after filtering
    print("\nAFTER FILTER COUNT:", len(data["links"]))
    print("AFTER FILTER LINKS (first 5):")
    print(data["links"][:5])

    return data


def main():
    base_url = "https://radetco.com/"

    input_path = Path("outputs/candidate_urls.json")
    output_path = Path("outputs/final_urls.json")

    if not input_path.exists():
        raise FileNotFoundError(
            "outputs/candidate_urls.json not found. Run your crawl step first to create it."
        )

    urls = json.loads(input_path.read_text(encoding="utf-8"))

    print(f"Loaded {len(urls)} candidate URLs.")

    result = pick_links_with_llm(base_url, urls)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("\n✅ Saved outputs/final_urls.json")


if __name__ == "__main__":
    main()