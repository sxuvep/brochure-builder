import json
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # Load environment variables from .env file
client = OpenAI()

SYSTEM_PROMPT = """
You summarize website pages for a company brochure.

Rules:
- Use ONLY the provided page text. Do not invent details.
- If something is not stated, wrtie "unknown".
- Be concise and fatual.
- Return ONLY valid JSON (no extra text, no markdown).

Return JSON in this format:
{
   "page_type": "about | products | solutions | industries | case_study | pricing | contact | other",
  "url": "https://...",
  "title": "page title",
  "summary": "2-4 sentences",
  "key_points": ["...", "..."],
  "facts": [
    {"claim": "...", "evidence": "exact short phrase from the text or unknown"}
  ]
  }
""".strip()

def summarize_one_page(page: dict) -> dict:
   user_payload = {
      "page_type": page.get("type","other"),
      "url": page.get("url",""),
      "title": page.get("title",""),
      "text": (page.get("text","")[:12000]), # limit to 12000 chars to fit in context window with the prompt
   }

   response = client.responses.create(
       model="gpt-4o-mini",
       input=[
          {"role":"system","content": SYSTEM_PROMPT},
          {"role":"user","content": json.dumps(user_payload, ensure_ascii=False)},
       ]
   )

   raw = response.output_text.strip()
   return json.loads(raw)

def main():
   input_dir = Path("outputs/pages")
   output_dir = Path("outputs/summaries")
   output_dir.mkdir(parents=True, exist_ok=True)

   files = sorted(input_dir.glob("*.json"))
   print(f"Found {len(files)} page files to summarize.\n")

   for f in files:
      page = json.loads(f.read_text(encoding="utf-8"))

      try:
          summary = summarize_one_page(page)
          output_path = output_dir / f.name
          output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
          print(f"Summarized {f.name} -> {output_path.name}")
      except Exception as e:
          print(f"Failed to summarize {f.name}: {e}")

if __name__ == "__main__":
    main()