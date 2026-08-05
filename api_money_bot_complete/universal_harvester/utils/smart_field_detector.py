"""
Smart Field Detector
====================
Uses JavaScript to extract all visible inputs, their labels (programmatic + visual proximity),
and match them to known field types. No OCR needed — reads label text directly from DOM.
Fills via 7 fallback selector strategies: id, name, data-testid, placeholder, aria-label, label text, className.
"""
from typing import Dict, Optional, List


class SmartFieldDetector:
    """
    Detects form fields by reading labels, placeholders, aria attributes, and nearby text
    for every visible input on the page. More comprehensive than DynamicFieldFinder
    because it captures visually-associated label text via JS.
    """

    FIELD_PATTERNS = {
        # FIX: Removed "mobile", "phone", "cell", "number" from email.
    # Email/Mobile combined fields still match because "email" is present in the label.
    # Phone fields without "email" in the label will NOT match as email anymore.
        "email": ["email", "e-mail", "mail address", "your email", "enter email", "email address"],
        "password": ["password", "passwd", "pwd", "pass"],
        "first_name": ["first name", "first", "given name", "fname", "forename"],
        "last_name": ["last name", "last", "surname", "family name", "lname"],
        "full_name": ["full name", "name", "your name", "display name"],
        "username": ["username", "user name", "user", "handle", "login"],
        "phone": ["phone", "telephone", "tel", "mobile", "cell"],
        "country": ["country", "nation", "region"],
        "city": ["city", "town", "locality"],
        "state": ["state", "province", "region"],
        "zip": ["zip", "zip code", "postal", "postcode", "post code"],
        "address": ["address", "street", "addr"],
        "company": ["company", "organization", "org", "business", "employer"],
        "website": ["website", "url", "site", "web"],
        "code": ["code", "otp", "verification code", "mfa", "2fa", "token"],
        "agree": ["agree", "terms", "accept", "consent", "toc"],
    }

    @classmethod
    def find_all_fields(cls, page) -> List[Dict]:
        """Use JS to find all visible inputs with their associated labels and metadata."""
        return page.evaluate("""() => {
            const inputs = document.querySelectorAll('input, select, textarea');
            const results = [];

            inputs.forEach(el => {
                // Skip hidden elements
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) return;

                // Check if visible
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return;

                // Gather metadata
                const type = el.getAttribute('type') || el.tagName.toLowerCase();
                const name = el.getAttribute('name') || '';
                const id = el.getAttribute('id') || '';
                const placeholder = el.getAttribute('placeholder') || '';
                const ariaLabel = el.getAttribute('aria-label') || '';
                const autocomplete = el.getAttribute('autocomplete') || '';
                const testid = el.getAttribute('data-testid') || el.getAttribute('data-test') || '';
                const className = el.getAttribute('class') || '';

                // Find associated label
                let labelText = '';

                // Method 1: aria-labelledby
                const labelledby = el.getAttribute('aria-labelledby');
                if (labelledby) {
                    const labelEl = document.getElementById(labelledby);
                    if (labelEl) labelText = labelEl.textContent.trim();
                }

                // Method 2: id -> label[for]
                if (!labelText && id) {
                    const labelFor = document.querySelector(`label[for="${CSS.escape(id)}"]`);
                    if (labelFor) labelText = labelFor.textContent.trim();
                }

                // Method 3: Wrapping label
                if (!labelText) {
                    const parent = el.closest('label');
                    if (parent) labelText = parent.textContent.trim();
                }

                // Method 4: Closest label-like element
                if (!labelText) {
                    const parent = el.parentElement;
                    if (parent) {
                        const labels = parent.querySelectorAll('label, span, div.label');
                        for (const lbl of labels) {
                            const txt = lbl.textContent.trim();
                            if (txt && txt.length < 100) {
                                labelText = txt;
                                break;
                            }
                        }
                    }
                }

                // Method 5: Previous sibling text
                if (!labelText) {
                    let prev = el.previousElementSibling;
                    while (prev) {
                        const txt = prev.textContent.trim();
                        if (txt) {
                            labelText = txt;
                            break;
                        }
                        prev = prev.previousElementSibling;
                    }
                }

                // Clean label text
                labelText = labelText.replace(/[\\s]+/g, ' ').trim();
                if (labelText.includes('*')) labelText = labelText.replace('*', '').trim();

                results.push({
                    type,
                    name,
                    id,
                    placeholder,
                    ariaLabel,
                    autocomplete,
                    testid,
                    className,
                    labelText,
                    isSelect: el.tagName === 'SELECT',
                    isCheckbox: type === 'checkbox',
                    rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height }
                });
            });

            return results;
        }""")

    @classmethod
    def classify_field(cls, field_info: Dict) -> Optional[str]:
        """Given a field info dict, return the best matching field type or None."""
        texts = []
        if field_info.get("labelText"):
            texts.append(field_info["labelText"].lower())
        if field_info.get("placeholder"):
            texts.append(field_info["placeholder"].lower())
        if field_info.get("ariaLabel"):
            texts.append(field_info["ariaLabel"].lower())
        if field_info.get("name"):
            texts.append(field_info["name"].lower())
        if field_info.get("autocomplete"):
            texts.append(field_info["autocomplete"].lower())
        if field_info.get("testid"):
            texts.append(field_info["testid"].lower())
        if field_info.get("id"):
            texts.append(field_info["id"].lower())

        combined = " ".join(texts)

        for field_type, patterns in cls.FIELD_PATTERNS.items():
            for pat in patterns:
                if pat in combined:
                    return field_type
        return None

    @classmethod
    def fill_all(cls, page, values: Dict[str, str]) -> Dict[str, bool]:
        """
        Fill all detected form fields with appropriate values.
        Uses 7 fallback selector strategies to find fields even without id/name.
        Returns dict of field_type -> whether it was filled.
        """
        fields = cls.find_all_fields(page)
        results = {}
        for field in fields:
            if field["isCheckbox"]:
                continue
            field_type = cls.classify_field(field)
            if field_type and field_type in values:
                try:
                    filled = False
                    value = values[field_type]

                    # Strategy 1: id selector
                    if not filled and field.get("id"):
                        try:
                            sel = f"#{field['id']}"
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                if field.get("isSelect"):
                                    try: el.select_option(label=value)
                                    except: el.select_option(index=1)
                                else:
                                    el.fill(value)
                                filled = True
                        except:
                            pass

                    # Strategy 2: name selector
                    if not filled and field.get("name"):
                        try:
                            sel = f'[name="{field["name"]}"]'
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                if field.get("isSelect"):
                                    try: el.select_option(label=value)
                                    except: el.select_option(index=1)
                                else:
                                    el.fill(value)
                                filled = True
                        except:
                            pass

                    # Strategy 3: data-testid
                    if not filled and field.get("testid"):
                        try:
                            sel = f'[data-testid="{field["testid"]}"]'
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                if field.get("isSelect"):
                                    try: el.select_option(label=value)
                                    except: el.select_option(index=1)
                                else:
                                    el.fill(value)
                                filled = True
                        except:
                            pass

                    # Strategy 4: placeholder (Playwright get_by_placeholder)
                    if not filled and field.get("placeholder"):
                        try:
                            el = page.get_by_placeholder(field["placeholder"], exact=False).first
                            if el and el.is_visible():
                                el.fill(value)
                                filled = True
                        except:
                            pass

                    # Strategy 5: aria-label (Playwright get_by_label)
                    if not filled and field.get("ariaLabel"):
                        try:
                            el = page.get_by_label(field["ariaLabel"], exact=False).first
                            if el and el.is_visible():
                                el.fill(value)
                                filled = True
                        except:
                            pass

                    # Strategy 6: label text (Playwright get_by_label)
                    if not filled and field.get("labelText"):
                        try:
                            el = page.get_by_label(field["labelText"], exact=False).first
                            if el and el.is_visible():
                                el.fill(value)
                                filled = True
                        except:
                            pass

                    # Strategy 7: className (last resort, query by class)
                    if not filled and field.get("className"):
                        try:
                            classes = field["className"].split()[:3]
                            sel = "." + ".".join(classes)
                            el = page.query_selector(sel)
                            if el and el.is_visible():
                                if field.get("isSelect"):
                                    try: el.select_option(label=value)
                                    except: el.select_option(index=1)
                                else:
                                    el.fill(value)
                                filled = True
                        except:
                            pass

                    results[field_type] = filled
                except Exception:
                    results[field_type] = False
        return results
