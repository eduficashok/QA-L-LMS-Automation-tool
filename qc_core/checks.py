import re
import time
from urllib.parse import urljoin, urlparse
from pathlib import Path
from typing import Dict, List, Any
from playwright.sync_api import Page, BrowserContext, TimeoutError as PlaywrightTimeoutError

from .config import SSO_LOGIN_PATTERNS, LINK_CHECK_TIMEOUT_MS


def is_auth_or_login_url(url: str) -> bool:
    """Detect whether a URL points to an SSO, login, or identity provider."""
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    return bool(re.search(r'/(login|signin|sso|saml|oauth|auth)(/|$)', parsed.path, re.I)) or any(
        host == domain or host.endswith('.' + domain)
        for domain in ('microsoftonline.com','duosecurity.com','okta.com','accounts.google.com'))



def check_images(page: Page, item_identifier: str, screenshots_dir: Path) -> List[Dict[str, Any]]:
    """
    Check all rendered images in the page content for loading failures.
    Catches images with missing src, or images that failed to decode (naturalWidth == 0).
    Captures screenshots for detected failures.
    """
    results = []

    # Query all images inside main content container or body
    raw_images = page.evaluate("""
    () => {
        const container = document.querySelector('.user_content') ||
                          document.querySelector('#content') ||
                          document.querySelector('main') ||
                          document.body;
        const images = Array.from(container.querySelectorAll('img'));
        return images.map((img, index) => {
            const rect = img.getBoundingClientRect();
            const rawSrc = img.getAttribute('src') || img.getAttribute('srcset') || '';
            const src = rawSrc.trim() ? (img.currentSrc || img.src || rawSrc) : '';
            const alt = img.getAttribute('alt') || '';
            const complete = img.complete;
            const naturalWidth = img.naturalWidth || 0;
            const naturalHeight = img.naturalHeight || 0;

            // An image is broken if:
            // 1. Missing / blank src
            // 2. complete is true but naturalWidth is 0 (failed to render)
            const isBroken = (!src || src.trim() === '') || (complete && naturalWidth === 0);

            return {
                index: index,
                src: src,
                alt: alt,
                complete: complete,
                naturalWidth: naturalWidth,
                naturalHeight: naturalHeight,
                isBroken: isBroken,
                width: Math.round(rect.width),
                height: Math.round(rect.height),
                visible: rect.width > 0 && rect.height > 0
            };
        });
    }
    """)

    for idx, img_data in enumerate(raw_images):
        src = img_data.get("src", "")
        alt = img_data.get("alt", "")
        is_broken = img_data.get("isBroken", False)
        natural_w = img_data.get("naturalWidth", 0)
        natural_h = img_data.get("naturalHeight", 0)

        # Skip tiny 1x1 tracker pixels or internal canvas UI icons if necessary,
        # but user content images should be checked thoroughly.
        screenshot_rel_path = None

        if is_broken:
            status = "FAIL"
            if not src or src.strip() == "":
                reason = "Broken Image: <img> tag has missing or empty src attribute"
            else:
                reason = f"Broken Image: Render failure (naturalWidth=0). Resource failed to load or render from: {src}"

            # Highlight element and capture screenshot
            try:
                page.evaluate(f"""
                () => {{
                    const container = document.querySelector('.user_content') ||
                                      document.querySelector('#content') ||
                                      document.querySelector('main') ||
                                      document.body;
                    const imgs = container.querySelectorAll('img');
                    if (imgs[{idx}]) {{
                        const target = imgs[{idx}];
                        target.style.outline = '4px solid #ef4444';
                        target.style.boxShadow = '0 0 15px rgba(239, 68, 68, 0.8)';
                        target.style.minWidth = '50px';
                        target.style.minHeight = '50px';
                        target.style.display = 'inline-block';
                        target.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                    }}
                }}
                """)
                time.sleep(0.3)

                sanitized_id = re.sub(r'[^a-zA-Z0-9_-]', '_', item_identifier)[:30]
                filename = f"broken_img_{sanitized_id}_{idx}_{int(time.time())}.png"
                full_screenshot_path = screenshots_dir / filename
                page.screenshot(path=str(full_screenshot_path), full_page=False)
                screenshot_rel_path = f"screenshots/{filename}"
            except Exception as e:
                # Fallback if screenshot highlight fails
                try:
                    sanitized_id = re.sub(r'[^a-zA-Z0-9_-]', '_', item_identifier)[:30]
                    filename = f"broken_img_{sanitized_id}_{idx}_{int(time.time())}.png"
                    full_screenshot_path = screenshots_dir / filename
                    page.screenshot(path=str(full_screenshot_path))
                    screenshot_rel_path = f"screenshots/{filename}"
                except Exception:
                    screenshot_rel_path = None
        elif not img_data.get("complete") or natural_w == 0:
            status = "NOT TESTED"
            reason = "Image loading or decoding was not completed"
        else:
            status = "PASS"
            reason = f"Image loaded successfully ({natural_w}x{natural_h} px)"

        results.append({
            "type": "image",
            "src": src,
            "alt": alt,
            "status": status,
            "reason": reason,
            "screenshot": screenshot_rel_path,
            "natural_width": natural_w,
            "natural_height": natural_h
        })

    return results


def check_links(page: Page, context: BrowserContext, base_url: str) -> List[Dict[str, Any]]:
    """
    Check links within the page content using the authenticated browser session.
    Adheres strictly to Requirement 6:
      - Authenticated session carries user cookies / SSO session
      - Does NOT classify login pages, access blocks (401/403), or timeouts as confirmed broken links.
      - Confirmed broken links: 404, 410, 500+, or DNS failure.
    """
    results = []

    # Query all links inside the content area
    raw_links = page.evaluate("""
    () => {
        const container = document.querySelector('.user_content') ||
                          document.querySelector('#content') ||
                          document.querySelector('main') ||
                          document.body;
        const links = Array.from(container.querySelectorAll('a[href]'));
        return links.map(a => ({
            href: a.getAttribute('href') || '',
            text: (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 120),
            title: a.getAttribute('title') || ''
        }));
    }
    """)

    # Deduplicate by href
    seen_urls = set()
    unique_links = []
    for link in raw_links:
        href = link.get("href", "").strip()
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)
        unique_links.append(link)

    for link in unique_links:
        href = link["href"]
        link_text = link["text"] or link["title"] or "(no anchor text)"

        # 1. Skip javascript links
        if href.lower().startswith("javascript:"):
            results.append({
                "type": "link",
                "href": href,
                "text": link_text,
                "status": "NOT TESTED",
                "category": "JAVASCRIPT",
                "reason": "Javascript link (not navigated)"
            })
            continue

        # 2. Email or Phone links
        if href.lower().startswith(("mailto:", "tel:")):
            results.append({
                "type": "link",
                "href": href,
                "text": link_text,
                "status": "NOT TESTED",
                "category": "PROTOCOL",
                "reason": f"Standard protocol link ({href.split(':')[0]})"
            })
            continue

        # 3. Anchor links on the same page (#anchor)
        if href.startswith("#"):
            target_id = href.lstrip("#")
            if not target_id:
                results.append({
                    "type": "link",
                    "href": href,
                    "text": link_text,
                    "status": "PASS",
                    "category": "LOCAL_ANCHOR",
                    "reason": "Top-of-page anchor"
                })
            else:
                exists = page.evaluate("(id) => Boolean(document.getElementById(id) || Array.from(document.getElementsByName(id)).length)", target_id)
                if exists:
                    results.append({
                        "type": "link",
                        "href": href,
                        "text": link_text,
                        "status": "PASS",
                        "category": "LOCAL_ANCHOR",
                        "reason": f"Local page anchor '#{target_id}' verified"
                    })
                else:
                    results.append({
                        "type": "link",
                        "href": href,
                        "text": link_text,
                        "status": "NOT TESTED",
                        "category": "LOCAL_ANCHOR",
                        "reason": f"Local anchor target '#{target_id}' element not found on current page"
                    })
            continue

        # 4. HTTP / HTTPS Links - resolve full URL
        target_url = urljoin(page.url, href)
        parsed = urlparse(target_url)

        if parsed.scheme not in ("http", "https"):
            results.append({
                "type": "link",
                "href": target_url,
                "text": link_text,
                "status": "NOT TESTED",
                "category": "UNKNOWN_SCHEME",
                "reason": f"Unsupported URI scheme: {parsed.scheme}"
            })
            continue

        # Use authenticated context request (inherits session cookies & headers)
        try:
            response = context.request.get(
                target_url,
                max_redirects=5,
                timeout=LINK_CHECK_TIMEOUT_MS,
                ignore_https_errors=False
            )

            status_code = response.status
            final_url = response.url

            # Check if redirected to login / SSO
            if is_auth_or_login_url(final_url) or is_auth_or_login_url(target_url):
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "NOT TESTED",
                    "category": "AUTH_REQUIRED",
                    "reason": f"Redirected to authentication portal ({final_url}). Not classified as broken."
                })
            elif status_code in (401, 403):
                # Access denied / auth blocked -> requirement 6: do NOT classify as broken
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "NOT TESTED",
                    "category": "ACCESS_RESTRICTED",
                    "reason": f"HTTP {status_code} Access Restricted / Auth Required. Not classified as broken."
                })
            elif status_code == 429:
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "NOT TESTED",
                    "category": "RATE_LIMITED",
                    "reason": "HTTP 429 Rate limited / bot challenge. Not classified as broken."
                })
            elif 200 <= status_code < 400:
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "PASS",
                    "category": "OK",
                    "reason": f"HTTP {status_code} OK"
                })
            elif status_code in (404, 410):
                # Confirmed broken link
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "FAIL",
                    "category": "BROKEN_LINK",
                    "reason": f"Confirmed broken link: HTTP {status_code} ({response.status_text})"
                })
            elif status_code >= 500:
                # Server error
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "NOT TESTED",
                    "category": "SERVER_ERROR",
                    "reason": f"Server unavailable during check: HTTP {status_code}"
                })
            else:
                # Other 4xx
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "NOT TESTED",
                    "category": "CLIENT_ERROR",
                    "reason": f"HTTP {status_code} ({response.status_text})"
                })

        except PlaywrightTimeoutError:
            # Requirement 6: Do not classify timeouts as broken links
            results.append({
                "type": "link",
                "href": target_url,
                "text": link_text,
                "status": "NOT TESTED",
                "category": "TIMEOUT",
                "reason": f"Request timed out after {int(LINK_CHECK_TIMEOUT_MS/1000)}s. Not classified as broken."
            })
        except Exception as e:
            err_str = str(e)
            if "ERR_NAME_NOT_RESOLVED" in err_str or "getaddrinfo failed" in err_str:
                # Confirmed broken domain/DNS failure
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "NOT TESTED",
                    "category": "DNS_FAILURE",
                    "reason": f"DNS lookup failed; requires recheck: ({err_str})"
                })
            elif "ERR_CONNECTION_REFUSED" in err_str:
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "NOT TESTED",
                    "category": "CONNECTION_REFUSED",
                    "reason": f"Connection refused; requires recheck: ({err_str})"
                })
            elif "timeout" in err_str.lower():
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "NOT TESTED",
                    "category": "TIMEOUT",
                    "reason": "Connection timed out. Not classified as broken."
                })
            else:
                results.append({
                    "type": "link",
                    "href": target_url,
                    "text": link_text,
                    "status": "NOT TESTED",
                    "category": "UNVERIFIED",
                    "reason": f"Unverified request exception: {err_str[:120]}. Not classified as broken."
                })

    return results


def check_embeds(page: Page) -> List[Dict[str, Any]]:
    """
    Requirement 7:
    Record videos and embeds, but mark them NOT TESTED unless actual playback was verified.
    Finds: <video>, <audio>, <iframe>, <embed>, <object>
    """
    raw_embeds = page.evaluate("""
    () => {
        const container = document.querySelector('.user_content') ||
                          document.querySelector('#content') ||
                          document.querySelector('main') ||
                          document.body;
        const list = [];

        // Videos
        container.querySelectorAll('video').forEach((v, i) => {
            const sources = Array.from(v.querySelectorAll('source')).map(s => s.src).filter(Boolean);
            list.push({
                kind: 'HTML5 Video',
                src: v.currentSrc || v.src || (sources.length > 0 ? sources.join(', ') : '(embedded video tag)'),
                title: v.getAttribute('title') || `Video #${i + 1}`
            });
        });

        // Audio
        container.querySelectorAll('audio').forEach((a, i) => {
            const sources = Array.from(a.querySelectorAll('source')).map(s => s.src).filter(Boolean);
            list.push({
                kind: 'HTML5 Audio',
                src: a.currentSrc || a.src || (sources.length > 0 ? sources.join(', ') : '(embedded audio tag)'),
                title: a.getAttribute('title') || `Audio #${i + 1}`
            });
        });

        // IFrames (YouTube, Vimeo, Kaltura, Canvas Studio, Panopto, etc.)
        container.querySelectorAll('iframe').forEach((f, i) => {
            const src = f.getAttribute('src') || '';
            const title = f.getAttribute('title') || f.getAttribute('name') || `IFrame Embed #${i + 1}`;
            // Ignore Canvas hidden helper iframes if any
            if (!src.includes('about:blank') && !f.classList.contains('hidden')) {
                list.push({
                    kind: 'IFrame Embed',
                    src: src,
                    title: title
                });
            }
        });

        // Embeds and Objects
        container.querySelectorAll('object, embed').forEach((o, i) => {
            const src = o.getAttribute('data') || o.getAttribute('src') || '';
            list.push({
                kind: 'Object/Embed',
                src: src,
                title: o.getAttribute('title') || `Embed #${i + 1}`
            });
        });

        return list;
    }
    """)

    results = []
    for item in raw_embeds:
        results.append({
            "type": "embed",
            "kind": item.get("kind", "Embed"),
            "src": item.get("src", ""),
            "title": item.get("title", ""),
            "status": "NOT TESTED",
            "reason": "Media/Embed detected. Automated playback verification disabled (manual playback check recommended)."
        })

    return results
