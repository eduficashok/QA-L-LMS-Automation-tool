import html
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


def _generate_html_report(
    course_url: str,
    scanned_results: List[Dict[str, Any]],
    skipped_items: List[Dict[str, Any]],
    output_dir: Path,
    scan_status: str = "INCOMPLETE",
    status_reason: str = "Overall coverage not verified"
) -> Path:
    """
    Generate a modern, self-contained HTML report with PASS, FAIL, NOT TESTED, and SKIPPED statuses,
    details of checks (images, links, embeds), reasons, and screenshot links.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"lms_qc_report_{timestamp}.html"
    report_path = output_dir / report_filename
    latest_path = output_dir / "latest_report.html"

    # Compute high-level statistics
    total_scanned_pages = len(scanned_results)
    total_skipped_items = len(skipped_items)

    total_images_checked = 0
    total_images_failed = 0
    total_links_checked = 0
    total_links_failed = 0
    total_embeds_found = 0
    total_screenshots = 0

    pages_passed = 0
    pages_failed = 0
    pages_with_embeds_only = 0

    for page in scanned_results:
        page_has_fail = False
        page_has_embeds = False

        # Images
        for img in page.get("images", []):
            total_images_checked += 1
            if img["status"] == "FAIL":
                total_images_failed += 1
                page_has_fail = True
            if img.get("screenshot"):
                total_screenshots += 1

        # Links
        for link in page.get("links", []):
            total_links_checked += 1
            if link["status"] == "FAIL":
                total_links_failed += 1
                page_has_fail = True

        # Embeds
        embeds = page.get("embeds", [])
        total_embeds_found += len(embeds)
        if len(embeds) > 0:
            page_has_embeds = True

        if page_has_fail:
            pages_failed += 1
            page["overall_status"] = "FAIL"
        elif page_has_embeds or page.get("error") or page.get("overall_status") == "NOT TESTED" or any(
            x.get("status") != "PASS" for x in page.get("images", []) + page.get("links", []) + page.get("embeds", [])
        ):
            pages_with_embeds_only += 1
            page["overall_status"] = "NOT TESTED"
        else:
            pages_passed += 1
            page["overall_status"] = "PASS"

    # Build HTML sections
    scanned_rows_html = []
    gallery_items_html = []

    for idx, page in enumerate(scanned_results, 1):
        status = page.get("overall_status", "PASS")
        status_badge_class = {
            "PASS": "badge-pass",
            "FAIL": "badge-fail",
            "NOT TESTED": "badge-not-tested"
        }.get(status, "badge-pass")

        module_name = html.escape(page.get("module_name") or "General / Course Root")
        title = html.escape(page.get("title") or f"Item #{idx}")
        url = html.escape(page.get("url") or "#")

        # Images breakdown
        img_details = []
        for img in page.get("images", []):
            img_status = img["status"]
            badge_cls = "badge-pass" if img_status == "PASS" else "badge-fail"
            img_src = html.escape(img.get("src", ""))
            reason = html.escape(img.get("reason", ""))
            screenshot_link = ""
            if img.get("screenshot"):
                s_path = html.escape(img["screenshot"])
                screenshot_link = f'<a href="{s_path}" target="_blank" class="screenshot-pill">📷 View Failure Screenshot</a>'
                gallery_items_html.append(f"""
                <div class="gallery-card">
                    <a href="{s_path}" target="_blank">
                        <img src="{s_path}" alt="Issue screenshot" loading="lazy">
                    </a>
                    <div class="gallery-info">
                        <strong>{title}</strong>
                        <p>{reason}</p>
                        <a href="{s_path}" target="_blank" class="link-btn">Open Full Screenshot &rarr;</a>
                    </div>
                </div>
                """)

            img_details.append(f"""
                <div class="detail-row">
                    <span class="badge {badge_cls}">{img_status}</span>
                    <span class="detail-text">
                        <span class="code-url" title="{img_src}">{img_src[:85] + ('...' if len(img_src) > 85 else '')}</span>
                        <br><small class="reason">{reason}</small>
                        {screenshot_link}
                    </span>
                </div>
            """)

        # Links breakdown
        link_details = []
        for lk in page.get("links", []):
            lk_status = lk["status"]
            badge_cls = {
                "PASS": "badge-pass",
                "FAIL": "badge-fail",
                "NOT TESTED": "badge-not-tested"
            }.get(lk_status, "badge-not-tested")
            href = html.escape(lk.get("href", ""))
            text = html.escape(lk.get("text", "") or "(No anchor text)")
            reason = html.escape(lk.get("reason", ""))

            link_details.append(f"""
                <div class="detail-row">
                    <span class="badge {badge_cls}">{lk_status}</span>
                    <span class="detail-text">
                        <strong>"{text}"</strong> &rarr; <a href="{href}" target="_blank" rel="noopener noreferrer" class="link-url">{href[:80] + ('...' if len(href) > 80 else '')}</a>
                        <br><small class="reason">{reason}</small>
                    </span>
                </div>
            """)

        # Embeds breakdown
        embed_details = []
        for emb in page.get("embeds", []):
            kind = html.escape(emb.get("kind", "Embed"))
            src = html.escape(emb.get("src", ""))
            title_emb = html.escape(emb.get("title", ""))
            reason = html.escape(emb.get("reason", ""))

            embed_details.append(f"""
                <div class="detail-row">
                    <span class="badge badge-not-tested">NOT TESTED</span>
                    <span class="detail-text">
                        <strong>{kind}:</strong> {title_emb} <br>
                        <span class="code-url">{src[:85] + ('...' if len(src) > 85 else '')}</span>
                        <br><small class="reason">{reason}</small>
                    </span>
                </div>
            """)

        images_html = "".join(img_details) if img_details else "<p class='empty-note'>No images found on page.</p>"
        links_html = "".join(link_details) if link_details else "<p class='empty-note'>No links found in content.</p>"
        embeds_html = "".join(embed_details) if embed_details else "<p class='empty-note'>No videos or embeds found.</p>"

        scanned_rows_html.append(f"""
        <article class="page-card status-{status.lower().replace(' ', '-')}">
            <header class="page-card-header">
                <div class="page-meta">
                    <span class="module-pill">{module_name}</span>
                    <h3 class="page-title"><a href="{url}" target="_blank" rel="noopener noreferrer">{title}</a></h3>
                    <span class="page-url">{url}</span>
                </div>
                <div class="page-status-box">
                    <span class="badge {status_badge_class} large-badge">{status}</span>
                </div>
            </header>

            <div class="card-sections">
                <details class="section-box" open>
                    <summary><strong>Images ({len(page.get("images", []))})</strong> &mdash; {sum(1 for i in page.get("images", []) if i["status"] == "FAIL")} Failed</summary>
                    <div class="section-content">
                        {images_html}
                    </div>
                </details>

                <details class="section-box" {("open" if any(l["status"] == "FAIL" for l in page.get("links", [])) else "")}>
                    <summary><strong>Links ({len(page.get("links", []))})</strong> &mdash; {sum(1 for l in page.get("links", []) if l["status"] == "FAIL")} Failed, {sum(1 for l in page.get("links", []) if l["status"] == "NOT TESTED")} Unverified/Auth</summary>
                    <div class="section-content">
                        {links_html}
                    </div>
                </details>

                <details class="section-box" {("open" if len(page.get("embeds", [])) > 0 else "")}>
                    <summary><strong>Videos &amp; Embeds ({len(page.get("embeds", []))})</strong> &mdash; Marked NOT TESTED</summary>
                    <div class="section-content">
                        {embeds_html}
                    </div>
                </details>
            </div>
        </article>
        """)

    # Skipped items table
    skipped_rows_html = []
    for s_idx, item in enumerate(skipped_items, 1):
        s_module = html.escape(item.get("module_name") or "General")
        s_title = html.escape(item.get("title") or f"Item #{s_idx}")
        s_type = html.escape(item.get("type") or "Unknown")
        s_reason = html.escape(item.get("skip_reason") or "Skipped by policy")
        s_url = item.get("url")
        url_link = f'<a href="{html.escape(s_url)}" target="_blank" rel="noopener noreferrer" class="link-url">{html.escape(s_url[:60])}</a>' if s_url else '<span class="text-muted">None</span>'

        skipped_rows_html.append(f"""
        <tr>
            <td><span class="badge badge-skipped">SKIPPED</span></td>
            <td><strong>{s_title}</strong></td>
            <td>{s_module}</td>
            <td><span class="type-pill">{s_type}</span></td>
            <td>{s_reason}</td>
            <td>{url_link}</td>
        </tr>
        """)

    scanned_content = "\n".join(scanned_rows_html) if scanned_rows_html else "<p class='empty-note'>No content pages were scanned.</p>"
    skipped_content = "\n".join(skipped_rows_html) if skipped_rows_html else "<tr><td colspan='6' class='text-center'>No items were skipped.</td></tr>"
    gallery_content = "\n".join(gallery_items_html) if gallery_items_html else "<p class='empty-note'>No failures detected &mdash; no issue screenshots captured! 🎉</p>"

    html_document = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LMS Quality Control (QC) Report &bull; Canvas Course</title>
    <style>
        :root {{
            --bg: #f8fafc;
            --surface: #ffffff;
            --surface-alt: #f1f5f9;
            --border: #e2e8f0;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #94a3b8;
            --pass-bg: #dcfce7;
            --pass-text: #166534;
            --pass-border: #86efac;
            --fail-bg: #fee2e2;
            --fail-text: #991b1b;
            --fail-border: #fca5a5;
            --not-tested-bg: #fef3c7;
            --not-tested-text: #92400e;
            --not-tested-border: #fcd34d;
            --skipped-bg: #f1f5f9;
            --skipped-text: #475569;
            --skipped-border: #cbd5e1;
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --radius: 10px;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
            --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.05);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text-primary);
            line-height: 1.5;
            padding-bottom: 4rem;
        }}

        header.top-bar {{
            background: #1e293b;
            color: #ffffff;
            padding: 1.75rem 2rem;
            box-shadow: var(--shadow-md);
        }}

        .header-container {{
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            flex-wrap: wrap;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
        }}

        .brand-title {{
            font-size: 1.5rem;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .meta-badges {{
            font-size: 0.875rem;
            color: #cbd5e1;
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
        }}

        .meta-tag {{
            background: rgba(255, 255, 255, 0.1);
            padding: 0.25rem 0.65rem;
            border-radius: 6px;
        }}

        main.container {{
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 1.5rem;
        }}

        /* KPI Grid */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .kpi-card {{
            background: var(--surface);
            border-radius: var(--radius);
            padding: 1.25rem;
            border: 1px solid var(--border);
            box-shadow: var(--shadow-sm);
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
        }}

        .kpi-value {{
            font-size: 2rem;
            font-weight: 800;
            line-height: 1.1;
        }}

        .kpi-label {{
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            font-weight: 600;
        }}

        .kpi-pass .kpi-value {{ color: var(--pass-text); }}
        .kpi-fail .kpi-value {{ color: var(--fail-text); }}
        .kpi-warn .kpi-value {{ color: var(--not-tested-text); }}

        /* Tabs & Filter Navigation */
        .tabs {{
            display: flex;
            gap: 0.5rem;
            border-bottom: 2px solid var(--border);
            margin-bottom: 1.5rem;
            overflow-x: auto;
        }}

        .tab-btn {{
            background: none;
            border: none;
            padding: 0.75rem 1.25rem;
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-secondary);
            cursor: pointer;
            border-bottom: 3px solid transparent;
            transition: all 0.2s ease;
        }}

        .tab-btn:hover {{
            color: var(--primary);
        }}

        .tab-btn.active {{
            color: var(--primary);
            border-bottom-color: var(--primary);
        }}

        .tab-content {{
            display: none;
        }}

        .tab-content.active {{
            display: block;
        }}

        /* Page Cards */
        .page-card {{
            background: var(--surface);
            border-radius: var(--radius);
            border: 1px solid var(--border);
            box-shadow: var(--shadow-sm);
            margin-bottom: 1.5rem;
            overflow: hidden;
        }}

        .status-fail {{
            border-left: 6px solid #ef4444;
        }}

        .status-pass {{
            border-left: 6px solid #10b981;
        }}

        .status-not-tested {{
            border-left: 6px solid #f59e0b;
        }}

        .page-card-header {{
            padding: 1.25rem 1.5rem;
            background: #ffffff;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
        }}

        .module-pill {{
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            background: var(--surface-alt);
            color: var(--text-secondary);
            padding: 0.2rem 0.55rem;
            border-radius: 4px;
            display: inline-block;
            margin-bottom: 0.35rem;
        }}

        .page-title {{
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--text-primary);
        }}

        .page-title a {{
            color: inherit;
            text-decoration: none;
        }}

        .page-title a:hover {{
            color: var(--primary);
            text-decoration: underline;
        }}

        .page-url {{
            font-size: 0.8rem;
            color: var(--text-muted);
            word-break: break-all;
        }}

        .card-sections {{
            padding: 1rem 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }}

        .section-box {{
            background: var(--surface-alt);
            border-radius: 8px;
            padding: 0.5rem 0.85rem;
        }}

        .section-box summary {{
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            padding: 0.35rem 0;
            outline: none;
            user-select: none;
        }}

        .section-content {{
            padding-top: 0.75rem;
            display: flex;
            flex-direction: column;
            gap: 0.65rem;
        }}

        .detail-row {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 0.65rem 0.85rem;
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
            font-size: 0.875rem;
        }}

        .detail-text {{
            flex: 1;
            word-break: break-word;
        }}

        .code-url {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.8rem;
            background: #e2e8f0;
            padding: 0.15rem 0.35rem;
            border-radius: 4px;
            color: #334155;
            display: inline-block;
            margin-top: 0.2rem;
        }}

        .link-url {{
            color: var(--primary);
            text-decoration: none;
        }}

        .link-url:hover {{
            text-decoration: underline;
        }}

        .reason {{
            color: var(--text-secondary);
            display: inline-block;
            margin-top: 0.2rem;
        }}

        .screenshot-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            margin-top: 0.35rem;
            background: #fee2e2;
            color: #991b1b;
            border: 1px solid #fca5a5;
            padding: 0.2rem 0.6rem;
            border-radius: 5px;
            font-size: 0.75rem;
            font-weight: 600;
            text-decoration: none;
        }}

        .screenshot-pill:hover {{
            background: #fecaca;
        }}

        /* Badges */
        .badge {{
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            padding: 0.2rem 0.55rem;
            border-radius: 5px;
            text-align: center;
            white-space: nowrap;
        }}

        .large-badge {{
            font-size: 0.875rem;
            padding: 0.35rem 0.85rem;
        }}

        .badge-pass {{
            background-color: var(--pass-bg);
            color: var(--pass-text);
            border: 1px solid var(--pass-border);
        }}

        .badge-fail {{
            background-color: var(--fail-bg);
            color: var(--fail-text);
            border: 1px solid var(--fail-border);
        }}

        .badge-not-tested {{
            background-color: var(--not-tested-bg);
            color: var(--not-tested-text);
            border: 1px solid var(--not-tested-border);
        }}

        .badge-skipped {{
            background-color: var(--skipped-bg);
            color: var(--skipped-text);
            border: 1px solid var(--skipped-border);
        }}

        .type-pill {{
            background: #e0e7ff;
            color: #3730a3;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
        }}

        /* Table */
        .table-wrap {{
            overflow-x: auto;
            background: var(--surface);
            border-radius: var(--radius);
            border: 1px solid var(--border);
            box-shadow: var(--shadow-sm);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
            text-align: left;
        }}

        th {{
            background: var(--surface-alt);
            padding: 0.85rem 1rem;
            font-weight: 700;
            color: var(--text-secondary);
            border-bottom: 1px solid var(--border);
        }}

        td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
        }}

        tr:last-child td {{
            border-bottom: none;
        }}

        /* Gallery */
        .gallery-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1.25rem;
        }}

        .gallery-card {{
            background: var(--surface);
            border: 1px solid var(--fail-border);
            border-radius: var(--radius);
            overflow: hidden;
            box-shadow: var(--shadow-sm);
            display: flex;
            flex-direction: column;
        }}

        .gallery-card img {{
            width: 100%;
            height: 180px;
            object-fit: cover;
            border-bottom: 1px solid var(--border);
            background: #000000;
            cursor: pointer;
        }}

        .gallery-info {{
            padding: 0.85rem;
            font-size: 0.8rem;
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
            flex: 1;
        }}

        .link-btn {{
            margin-top: auto;
            color: var(--primary);
            text-decoration: none;
            font-weight: 600;
            font-size: 0.8rem;
        }}

        .empty-note {{
            color: var(--text-muted);
            font-size: 0.875rem;
            font-style: italic;
            padding: 0.5rem 0;
        }}

        .safety-callout {{
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: var(--radius);
            padding: 1rem 1.25rem;
            margin-bottom: 1.5rem;
            font-size: 0.875rem;
            color: #1e40af;
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
    </style>
</head>
<body>
    <header class="top-bar">
        <div class="header-container">
            <div>
                <h1 class="brand-title">🔍 LMS QC Report &bull; Canvas Course 350</h1>
                <p style="font-size: 0.9rem; color: #94a3b8; margin-top: 0.25rem;">Quality Control Audit for Rendered Images, Verified Links &amp; Media Embeds</p>
            </div>
            <div class="meta-badges">
                <span class="meta-tag">📅 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
                <span class="meta-tag">🎯 Course 350</span>
                <span class="meta-tag">🛡️ Read-Only Scan</span>
            </div>
        </div>
    </header>

    <main class="container">
        <div class="safety-callout">
            <span style="font-size: 1.25rem;">🛡️</span>
            <div>
                <strong>Non-Destructive Inspection:</strong> This tool only executed read-only checks. No assignments were submitted, no discussions posted, and no course content was modified or published.
            </div>
        </div>

        <!-- KPI Metrics Grid -->
        <section class="kpi-grid">
            <div class="kpi-card">
                <span class="kpi-value">{total_scanned_pages}</span>
                <span class="kpi-label">Pages Scanned</span>
            </div>
            <div class="kpi-card">
                <span class="kpi-value">{total_skipped_items}</span>
                <span class="kpi-label">Items Skipped</span>
            </div>
            <div class="kpi-card kpi-pass">
                <span class="kpi-value">{pages_passed}</span>
                <span class="kpi-label">Clean Pages (PASS)</span>
            </div>
            <div class="kpi-card kpi-fail">
                <span class="kpi-value">{total_images_failed}</span>
                <span class="kpi-label">Broken Images (FAIL)</span>
            </div>
            <div class="kpi-card kpi-fail">
                <span class="kpi-value">{total_links_failed}</span>
                <span class="kpi-label">Broken Links (FAIL)</span>
            </div>
            <div class="kpi-card kpi-warn">
                <span class="kpi-value">{total_embeds_found}</span>
                <span class="kpi-label">Videos/Embeds (NOT TESTED)</span>
            </div>
        </section>

        <!-- Navigation Tabs -->
        <nav class="tabs">
            <button class="tab-btn active" onclick="switchTab('scanned')">Scanned Pages ({total_scanned_pages})</button>
            <button class="tab-btn" onclick="switchTab('skipped')">Skipped Items ({total_skipped_items})</button>
            <button class="tab-btn" onclick="switchTab('gallery')">Screenshot Gallery ({total_screenshots})</button>
        </nav>

        <!-- TAB 1: Scanned Pages -->
        <section id="tab-scanned" class="tab-content active">
            {scanned_content}
        </section>

        <!-- TAB 2: Skipped Items -->
        <section id="tab-skipped" class="tab-content">
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Item Title</th>
                            <th>Module</th>
                            <th>Item Type</th>
                            <th>Skip Reason</th>
                            <th>Original Link</th>
                        </tr>
                    </thead>
                    <tbody>
                        {skipped_content}
                    </tbody>
                </table>
            </div>
        </section>

        <!-- TAB 3: Issue Screenshot Gallery -->
        <section id="tab-gallery" class="tab-content">
            <div class="gallery-grid">
                {gallery_content}
            </div>
        </section>
    </main>

    <script>
        function switchTab(tabId) {{
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            const targetTab = document.getElementById('tab-' + tabId);
            if (targetTab) {{
                targetTab.classList.add('active');
            }}
            event.target.classList.add('active');
        }}
    </script>
</body>
</html>
"""

    report_path.write_text(html_document, encoding="utf-8")
    shutil.copy2(report_path, latest_path)

    return report_path


def generate_html_report(course_url, scanned_results, skipped_items, output_dir,
                         scan_status="INCOMPLETE", status_reason="Overall coverage not verified"):
    report = _generate_html_report(course_url, scanned_results, skipped_items, output_dir)
    banner = ('<section id="scan-outcome" style="padding:24px;background:#fff3cd;color:#222">'
              '<h1>SCAN STATUS: ' + html.escape(scan_status) + '</h1><p>'
              + html.escape(status_reason) + '</p></section>')
    contents = report.read_text(encoding="utf-8")
    import re
    contents = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + banner, contents, count=1)
    report.write_text(contents, encoding="utf-8")
    (output_dir / "latest_report.html").write_text(contents, encoding="utf-8")
    print(f"[*] OVERALL SCAN STATUS: {scan_status} - {status_reason}")
    return report
