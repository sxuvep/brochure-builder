# Brochure Builder

Generate a professional company brochure by crawling a website, selecting key pages, summarizing content with OpenAI, and drafting polished brochure copy — all from a Gradio UI.

## How it works

1. **Crawl** — Fetches the homepage and extracts all internal links.
2. **Pick** — An LLM selects the most brochure-relevant pages (About, Products, Case Studies, Pricing, Contact, etc.).
3. **Approve** — You review and check/uncheck the links before anything is extracted.
4. **Extract** — Pages are downloaded and parsed in parallel (up to 5 workers).
5. **Summarize** — Each page is summarized by OpenAI in parallel (up to 3 concurrent calls).
6. **Build** — A final LLM pass synthesizes summaries into a structured Markdown brochure.
7. **Export** — Download the brochure as `.md` or `.docx`.

## Requirements

- Python 3.10+
- An OpenAI API key

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the project root:

```
OPENAI_API_KEY=sk-...
```

3. Start the app:

```bash
python src/gradio_app.py
```

Then open `http://127.0.0.1:7861` in your browser.

## Usage

| Step       | What to do                                                                                                          |
| ---------- | ------------------------------------------------------------------------------------------------------------------- |
| **Step 1** | Enter the company URL. Optionally add context (target audience, key differentiators). Click **Analyze Links →**.    |
| **Step 2** | Review the pre-selected links. Use **Select All / Deselect All** to adjust. Click **Generate Brochure →**.          |
| **Step 3** | Watch the live processing log. When done, preview the brochure, edit it in-place, and download as `.md` or `.docx`. |

Use the **Section Controls** accordion to toggle sections on/off or regenerate a single section from the same page summaries.

## Limitations

- **JavaScript-heavy sites** (e.g. Amazon, SPAs) return no static links — the crawler uses `requests` + `BeautifulSoup` and does not execute JavaScript.
- **Bot-protected sites** (Cloudflare, CAPTCHAs) will block the crawler. This tool works best on standard B2B/SMB company websites.
- Pages returning 403/429 are skipped with a warning in the processing log.

## Project structure

```
src/
  gradio_app.py        # Gradio UI — main entrypoint
  crawl_extract.py     # Homepage crawler
  llm_pick_links.py    # LLM link selector
  extract_pages.py     # Parallel page extractor
  summarize_pages.py   # Per-page summarizer
  build_brochure.py    # Brochure builder + DOCX exporter
outputs/               # Intermediate JSON files and final brochure
```
