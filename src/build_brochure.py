import json
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # Load environment variables from .env file
client = OpenAI()

SYSTEM_PROMPT = """
You are a professional business writer creating a company brochure in Markdown.

You are given structured page summaries (each has summary, key_points, facts, url/title).
Your job is to synthesize them into a strong brochure.

Rules:
- Use ONLY the provided summaries. Do NOT invent facts or numbers.
- Do NOT write phrases like "not available", "not provided", "unknown", or similar.
  If details are missing, simply skip them or write a more general statement grounded in what IS present.
- You MAY combine information across multiple summaries to form complete sections.
- Prefer concrete claims that appear in the summaries' facts/key_points.
- Output ONLY Markdown (no JSON, no extra commentary).

Write in this structure (omit any section that would be empty):
# <Company Name>
## Overview
## Offerings
## Who We Serve
## Why Us
## Proof & Results
## How It Works
## Get Started / Contact

Formatting requirements:
- Use short paragraphs.
- Use bullet lists for offerings and who-we-serve.
- In "Proof & Results", mention awards/case studies if present (no made-up metrics).
- End with a clear call to action and include the website + contact URL if available.
""".strip()

def extract_website(summaries):
  for s in summaries:
    url = s.get("url", "")
    if url:
      parsed = urlparse(url)
      return f"{parsed.scheme}://{parsed.netloc}"
  return ""

def extract_company_name(summaries):
    for s in summaries:
        if s.get("page_type") == "about":
            title = s.get("title")
            if title:
                return title.split("|")[0].strip()
    # fallback to first title
    if summaries:
        return summaries[0].get("title", "").split("|")[0].strip()
    return "Company"

def load_summaries(summaries_dir : Path) -> list[dict]:
  """
  Reads all summary JSON files from outputs/summaries/ and returns a list of dicts.
  """
  files = sorted(summaries_dir.glob(".json"))
  summaries = []
  for f in files:
    summaries.append(json.loads(f.read_text(encoding="utf-8")))
  return summaries

def build_brochure_markdown(company_name: str, website:str, summaries: list[dict]) -> str:
  """
  Calls OpenAI once to synthesize the brochure from summaries and returns Markdown text.
  """
  user_payload = {
    "company_name": company_name,
    "website": website,
    "section_hints": {
        "Overview": ["about"],
        "Offerings": ["solutions", "products", "other"],
        "Who We Serve": ["industries"],
        "Proof & Results": ["case_study", "other"],
        "How It Works": ["platform", "other"],
        "Get Started / Contact": ["contact", "pricing"]
    },
    "summaries": summaries,
}

  response = client.responses.create(
      model="gpt-4o-mini",
      input=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
      ]
  )
  return response.output_text.strip() # the generated brochure in Markdown format which is by default in the output_text field

def main():
  summaries_dir = Path("outputs/summaries")
  output_path = Path("outputs/brochure.md")

  if not summaries_dir.exists():
    raise FileNotFoundError("outputs/summaries not found. Run summarize_pages.py first to generate page summaries.")
  summaries = load_summaries(summaries_dir)

  company_name = extract_company_name(summaries)
  website = extract_website(summaries)
  print(f"Loaded {len(summaries)} page summaries. Building brochure...\n")

  brochure_md = build_brochure_markdown(company_name, website, summaries)
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(brochure_md, encoding="utf-8")

  print("Wrote outputs/brochure.md")

if __name__ == "__main__":
  main()