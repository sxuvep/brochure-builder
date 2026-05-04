import ipaddress
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import gradio as gr

from build_brochure import (
    build_brochure_markdown,
    client as brochure_client,
    export_to_docx,
    extract_company_name,
    extract_website,
)
from crawl_extract import save_candidate_urls
from extract_pages import extract_pages_from_links
from llm_pick_links import pick_links_with_llm
from summarize_pages import summarize_one_page

SECTION_ORDER = [
    "Overview",
    "Offerings",
    "Who We Serve",
    "Why Us",
    "Proof & Results",
    "How It Works",
    "Get Started / Contact",
]


def normalize_and_validate_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Please enter a company website URL.")

    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// and https:// URLs are supported.")
    if not parsed.netloc:
        raise ValueError("Please enter a valid URL including domain.")

    host = parsed.hostname or ""
    if host.lower() == "localhost":
        raise ValueError("Local/private URLs are not allowed.")

    try:
        ip_obj = ipaddress.ip_address(host)
    except ValueError:
        ip_obj = None

    if ip_obj and (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local):
        raise ValueError("Local/private URLs are not allowed.")

    base = f"{parsed.scheme}://{parsed.netloc}"
    return f"{base}/"


def _append_log(logs: list[str], message: str) -> str:
    logs.append(message)
    return "\n".join(logs)


def _clear_json_files(folder: Path) -> None:
    if not folder.exists():
        return
    for file_path in folder.glob("*.json"):
        file_path.unlink(missing_ok=True)


def _parse_sections(markdown_text: str) -> tuple[str, list[str], dict[str, str]]:
    title = "# Company Brochure"
    order: list[str] = []
    sections: dict[str, str] = {}
    current = None
    body_lines: list[str] = []

    for line in (markdown_text or "").splitlines():
        if line.startswith("# ") and title == "# Company Brochure":
            title = line.strip()
            continue
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(body_lines).strip()
            current = line[3:].strip()
            order.append(current)
            body_lines = []
            continue
        if current is not None:
            body_lines.append(line)

    if current is not None:
        sections[current] = "\n".join(body_lines).strip()

    return title, order, sections


def _assemble_sections(title: str, order: list[str], sections: dict[str, str], enabled: list[str] | None = None) -> str:
    enabled_set = set(enabled) if enabled else None
    chunks = [title]
    for name in order:
        if name not in sections:
            continue
        if enabled_set is not None and name not in enabled_set:
            continue
        content = sections[name].strip()
        if not content:
            continue
        chunks.append(f"## {name}\n{content}")
    return "\n\n".join(chunks).strip() + "\n"


def _filter_brochure_sections(markdown_text: str, enabled_sections: list[str]) -> str:
    title, order, sections = _parse_sections(markdown_text)
    return _assemble_sections(title, order, sections, enabled_sections)


def _build_evidence_markdown(summaries: list[dict]) -> str:
    if not summaries:
        return "No summaries yet."

    lines = ["## Evidence", ""]
    for idx, summary in enumerate(summaries, start=1):
        page_type = summary.get("page_type", "other")
        title = summary.get("title") or "Untitled page"
        url = summary.get("url", "")

        lines.append(f"### {idx}. {page_type} - {title}")
        if url:
            lines.append(f"- URL: {url}")

        for point in summary.get("key_points", [])[:3]:
            lines.append(f"- Key point: {point}")

        for fact in summary.get("facts", [])[:3]:
            claim = fact.get("claim", "")
            evidence = fact.get("evidence", "")
            if claim:
                lines.append(f"- Fact: {claim}")
            if evidence:
                lines.append(f"- Evidence: {evidence}")
        lines.append("")

    return "\n".join(lines).strip()


def analyze_site(base_url_input: str):
    logs: list[str] = []
    try:
        base_url = normalize_and_validate_url(base_url_input)
        outputs_dir = Path("outputs")
        candidate_urls_path = outputs_dir / "candidate_urls.json"
        final_urls_path = outputs_dir / "final_urls.json"

        _append_log(logs, f"Stage 1/2: Crawling links from {base_url}")
        candidate_urls = save_candidate_urls(base_url, candidate_urls_path)
        _append_log(logs, f"Found {len(candidate_urls)} candidate links")

        _append_log(logs, "Stage 2/2: Picking brochure links with LLM")
        final_links_payload = pick_links_with_llm(base_url, candidate_urls)
        final_urls_path.write_text(json.dumps(final_links_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        selected_links = final_links_payload.get("links", [])
        if not selected_links:
            raise ValueError("No links were selected by the model.")

        choices = []
        lookup: dict[str, dict] = {}
        selected_values = []
        for item in selected_links:
            page_type = item.get("type", "other")
            url = item.get("url", "")
            title = item.get("title") or url
            value = json.dumps(item, ensure_ascii=False)
            label = f"[{page_type}] {title}"
            choices.append((label, value))
            lookup[value] = item
            selected_values.append(value)

        _append_log(logs, f"Ready for review: {len(selected_links)} links pre-selected")
        return (
            "\n".join(logs),
            gr.update(choices=choices, value=selected_values),
            lookup,
            selected_values,
            gr.update(visible=True),
        )
    except Exception as exc:
        _append_log(logs, f"Error: {exc}")
        return "\n".join(logs), gr.update(choices=[], value=[]), {}, [], gr.update(visible=False)


def generate_brochure_stream(approved_values: list[str], section_selection: list[str], link_lookup: dict[str, dict], company_context: str = ""):
    logs: list[str] = []
    evidence = "No summaries yet."
    brochure_text = ""
    brochure_path = None
    summaries: list[dict] = []

    try:
        if not link_lookup:
            raise ValueError("Run Analyze Links first.")

        selected_links = [link_lookup[val] for val in approved_values if val in link_lookup]
        if not selected_links:
            raise ValueError("Select at least one approved link.")

        outputs_dir = Path("outputs")
        pages_dir = outputs_dir / "pages"
        summaries_dir = outputs_dir / "summaries"
        brochure_file_path = outputs_dir / "brochure.md"

        pages_dir.mkdir(parents=True, exist_ok=True)
        summaries_dir.mkdir(parents=True, exist_ok=True)
        _clear_json_files(pages_dir)
        _clear_json_files(summaries_dir)

        _append_log(logs, f"Step 1/3: Extracting {len(selected_links)} approved pages")
        yield "\n".join(logs), brochure_text, evidence, brochure_path, summaries, brochure_text, gr.update(visible=False)

        page_files = extract_pages_from_links(selected_links, pages_dir)
        if not page_files:
            raise ValueError("No pages could be extracted from approved links.")

        _append_log(logs, f"Extracted {len(page_files)} pages")
        yield "\n".join(logs), brochure_text, evidence, brochure_path, summaries, brochure_text, gr.update(visible=False)

        sorted_files = sorted(page_files)
        total = len(sorted_files)
        summaries_by_name: dict[str, dict] = {}
        completed_count = 0

        _append_log(logs, f"Step 2/3: Summarizing {total} pages (up to 3 at a time)")
        yield "\n".join(logs), brochure_text, evidence, brochure_path, summaries, brochure_text, gr.update(visible=False)

        def _summarize_file(page_file: Path) -> tuple[Path, dict]:
            page = json.loads(page_file.read_text(encoding="utf-8"))
            return page_file, summarize_one_page(page)

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_file = {executor.submit(_summarize_file, f): f for f in sorted_files}
            for future in as_completed(future_to_file):
                page_file, summary = future.result()
                summaries_by_name[page_file.name] = summary
                summary_path = summaries_dir / page_file.name
                summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
                completed_count += 1
                evidence = _build_evidence_markdown(list(summaries_by_name.values()))
                _append_log(logs, f"Summarized {completed_count}/{total}: {summary.get('title', page_file.name)}")
                yield "\n".join(logs), brochure_text, evidence, brochure_path, list(summaries_by_name.values()), brochure_text, gr.update(visible=False)

        summaries = [summaries_by_name[f.name] for f in sorted_files if f.name in summaries_by_name]

        _append_log(logs, "Step 3/3: Building brochure...")
        yield "\n".join(logs), brochure_text, evidence, brochure_path, summaries, brochure_text, gr.update(visible=False)

        company_name = extract_company_name(summaries)
        website = extract_website(summaries)
        brochure_text = build_brochure_markdown(company_name, website, summaries, company_context)

        if section_selection:
            brochure_text = _filter_brochure_sections(brochure_text, section_selection)

        brochure_file_path.write_text(brochure_text, encoding="utf-8")
        brochure_path = str(brochure_file_path)
        _append_log(logs, f"Done. Brochure saved to {brochure_path}")
        yield "\n".join(logs), brochure_text, evidence, brochure_path, summaries, brochure_text, gr.update(visible=True)
    except Exception as exc:
        _append_log(logs, f"Error: {exc}")
        yield "\n".join(logs), brochure_text, evidence, brochure_path, summaries, brochure_text, gr.update(visible=False)


def regenerate_section(
    section_name: str,
    section_selection: list[str],
    summaries: list[dict],
    current_brochure: str,
    current_timeline: str,
):
    logs = [line for line in (current_timeline or "").splitlines() if line.strip()]
    try:
        if not section_name:
            raise ValueError("Choose a section to regenerate.")
        if not summaries:
            raise ValueError("No summaries available yet.")
        if not current_brochure.strip():
            raise ValueError("Generate a brochure first.")

        prompt = (
            "Rewrite exactly one brochure section in Markdown.\n"
            f"Section name: {section_name}\n"
            "Use only provided summaries and facts.\n"
            "Return only this format:\n"
            f"## {section_name}\n"
            "<section content>"
        )

        response = brochure_client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": "You are a precise B2B brochure editor."},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": prompt,
                            "summaries": summaries,
                            "existing_brochure": current_brochure,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )

        regenerated = response.output_text.strip()
        if regenerated.startswith(f"## {section_name}"):
            regenerated = regenerated[len(f"## {section_name}") :].strip()

        title, order, sections = _parse_sections(current_brochure)
        if section_name not in order:
            order.append(section_name)
        sections[section_name] = regenerated

        updated = _assemble_sections(title, order, sections, section_selection)
        Path("outputs").mkdir(parents=True, exist_ok=True)
        brochure_path = Path("outputs/brochure.md")
        brochure_path.write_text(updated, encoding="utf-8")

        _append_log(logs, f"Regenerated section: {section_name}")
        return "\n".join(logs), updated, str(brochure_path), updated
    except Exception as exc:
        _append_log(logs, f"Regenerate error: {exc}")
        return "\n".join(logs), current_brochure, None, current_brochure


def build_interface() -> gr.Blocks:
    with gr.Blocks(title="Brochure Builder") as demo:
        gr.Markdown("# Brochure Builder")

        link_lookup_state = gr.State({})
        summaries_state = gr.State([])
        brochure_state = gr.State("")
        link_choices_state = gr.State([])

        # ── Step 1: Configure ──────────────────────────────────────
        gr.Markdown("### Step 1 — Configure")
        with gr.Row():
            url_input = gr.Textbox(
                label="Company URL",
                placeholder="https://example.com",
                scale=4,
            )
            analyze_button = gr.Button("Analyze Links →", variant="secondary", scale=1)
        company_context_input = gr.Textbox(
            label="Company Context (optional)",
            placeholder="e.g. Target audience: hospital procurement teams. Key differentiator: fastest turnaround.",
            lines=2,
        )

        timeline_output = gr.Textbox(label="Processing Log", lines=5, interactive=False)

        # ── Step 2: Approve Links (hidden until Analyze completes) ─
        with gr.Group(visible=False) as step2_group:
            gr.Markdown("### Step 2 — Approve Links")
            with gr.Row():
                select_all_btn = gr.Button("Select All", size="sm", variant="secondary")
                deselect_all_btn = gr.Button("Deselect All", size="sm", variant="secondary")
            approved_links = gr.CheckboxGroup(label="", choices=[])
            generate_button = gr.Button("Generate Brochure →", variant="primary")

        # ── Step 3: Output (hidden until Generate completes) ───────
        with gr.Group(visible=False) as step3_group:
            gr.Markdown("### Step 3 — Output")
            with gr.Row():
                brochure_download = gr.File(label="Download .md")
                docx_download = gr.File(label="Download .docx")
            with gr.Tabs():
                with gr.Tab("Preview"):
                    brochure_output = gr.Markdown()
                with gr.Tab("Edit Brochure"):
                    brochure_edit = gr.Textbox(
                        label="Markdown Source",
                        lines=30,
                        interactive=True,
                    )
                    save_edits_button = gr.Button("Save Edits")
                with gr.Tab("Evidence"):
                    evidence_output = gr.Markdown()
            with gr.Accordion("Section Controls", open=False):
                section_selection = gr.CheckboxGroup(
                    label="Included Sections",
                    choices=SECTION_ORDER,
                    value=SECTION_ORDER,
                )
                with gr.Row():
                    regenerate_section_name = gr.Dropdown(
                        label="Regenerate Section",
                        choices=SECTION_ORDER,
                        value="Overview",
                    )
                    regenerate_button = gr.Button("Regenerate", variant="secondary")

        # ── Internal helpers ───────────────────────────────────────
        def _save_edits(edited_text: str):
            Path("outputs").mkdir(parents=True, exist_ok=True)
            Path("outputs/brochure.md").write_text(edited_text, encoding="utf-8")
            return edited_text, edited_text, str(Path("outputs/brochure.md"))

        def _export_docx(brochure_text: str):
            if not brochure_text.strip():
                return None
            docx_path = Path("outputs/brochure.docx")
            export_to_docx(brochure_text, docx_path)
            return str(docx_path)

        # ── Events ─────────────────────────────────────────────────
        analyze_button.click(
            fn=analyze_site,
            inputs=[url_input],
            outputs=[timeline_output, approved_links, link_lookup_state, link_choices_state, step2_group],
        )

        select_all_btn.click(
            fn=lambda choices: choices,
            inputs=[link_choices_state],
            outputs=[approved_links],
        )

        deselect_all_btn.click(
            fn=lambda: [],
            inputs=[],
            outputs=[approved_links],
        )

        generate_button.click(
            fn=generate_brochure_stream,
            inputs=[approved_links, section_selection, link_lookup_state, company_context_input],
            outputs=[
                timeline_output,
                brochure_output,
                evidence_output,
                brochure_download,
                summaries_state,
                brochure_state,
                step3_group,
            ],
        ).then(
            fn=lambda t: t,
            inputs=[brochure_state],
            outputs=[brochure_edit],
        ).then(
            fn=_export_docx,
            inputs=[brochure_state],
            outputs=[docx_download],
        )

        regenerate_button.click(
            fn=regenerate_section,
            inputs=[
                regenerate_section_name,
                section_selection,
                summaries_state,
                brochure_state,
                timeline_output,
            ],
            outputs=[timeline_output, brochure_output, brochure_download, brochure_state],
        ).then(
            fn=lambda t: t,
            inputs=[brochure_state],
            outputs=[brochure_edit],
        ).then(
            fn=_export_docx,
            inputs=[brochure_state],
            outputs=[docx_download],
        )

        save_edits_button.click(
            fn=_save_edits,
            inputs=[brochure_edit],
            outputs=[brochure_output, brochure_state, brochure_download],
        ).then(
            fn=_export_docx,
            inputs=[brochure_state],
            outputs=[docx_download],
        )

    return demo


if __name__ == "__main__":
    app = build_interface()
    app.launch()
