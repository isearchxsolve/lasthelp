"""Advanced field detection for unusual DOM structures."""
from typing import Optional, List, Dict
from playwright.sync_api import Page, ElementHandle


class AdvancedFieldFinder:
    """Extra strategies for sites that break standard detection."""

    @staticmethod
    def find_by_aria_label(page: Page, field_type: str) -> Optional[ElementHandle]:
        """Find inputs by aria-label or aria-labelledby."""
        aria_map = {
            "email": ["email", "e-mail", "mail", "email address", "your email"],
            "password": ["password", "pass", "your password"],
            "username": ["username", "user name", "login", "your username"],
            "first_name": ["first name", "given name", "fname"],
            "last_name": ["last name", "surname", "family name", "lname"],
        }
        keywords = aria_map.get(field_type, [field_type])

        for kw in keywords:
            # aria-label
            el = page.query_selector(f'input[aria-label*="{kw}" i]')
            if el:
                return el
            # aria-labelledby (check referenced element text)
            labelled = page.query_selector_all('[aria-labelledby]')
            for el in labelled:
                labelled_by = el.get_attribute("aria-labelledby")
                if labelled_by:
                    label_el = page.query_selector(f"#{labelled_by}")
                    if label_el and kw.lower() in label_el.inner_text().lower():
                        return el
        return None

    @staticmethod
    def find_by_placeholder(page: Page, field_type: str) -> Optional[ElementHandle]:
        """Find inputs by placeholder text."""
        placeholder_map = {
            "email": ["email", "e-mail", "mail", "your@email.com", "example@email.com"],
            "password": ["password", "pass", "your password", "********"],
            "username": ["username", "user name", "login"],
            "first_name": ["first name", "given name", "john"],
            "last_name": ["last name", "surname", "doe"],
        }
        keywords = placeholder_map.get(field_type, [field_type])

        for kw in keywords:
            el = page.query_selector(f'input[placeholder*="{kw}" i]')
            if el:
                return el
        return None

    @staticmethod
    def find_by_surrounding_text(page: Page, field_type: str) -> Optional[ElementHandle]:
        """Find inputs by text in parent or sibling elements."""
        text_map = {
            "email": ["email", "e-mail", "mail address"],
            "password": ["password", "create password", "set password"],
            "username": ["username", "user name", "choose a username"],
            "first_name": ["first name", "given name"],
            "last_name": ["last name", "surname", "family name"],
        }
        keywords = text_map.get(field_type, [field_type])

        inputs = page.query_selector_all("input, textarea")
        for inp in inputs:
            # Check parent text
            parent_text = inp.evaluate("""
                el => {
                    let parent = el.closest('div, fieldset, form, label, td');
                    return parent ? parent.innerText : '';
                }
            """) or ""

            # Check sibling label
            sibling_text = inp.evaluate("""
                el => {
                    let prev = el.previousElementSibling;
                    let next = el.nextElementSibling;
                    return (prev ? prev.innerText : '') + ' ' + (next ? next.innerText : '');
                }
            """) or ""

            combined = (parent_text + " " + sibling_text).lower()
            for kw in keywords:
                if kw.lower() in combined:
                    return inp
        return None

    @staticmethod
    def find_by_inputmode(page: Page, field_type: str) -> Optional[ElementHandle]:
        """Find by HTML5 inputmode or type hints."""
        mode_map = {
            "email": 'input[inputmode="email"], input[type="email"]',
            "password": 'input[type="password"]',
            "username": 'input[inputmode="verbatim"], input[type="text"][name*="user" i]',
        }
        selector = mode_map.get(field_type)
        if selector:
            return page.query_selector(selector)
        return None

    @staticmethod
    def find_by_autocomplete(page: Page, field_type: str) -> Optional[ElementHandle]:
        """Find by autocomplete attribute (very reliable when present)."""
        auto_map = {
            "email": 'input[autocomplete="email"], input[autocomplete="username email"]',
            "password": 'input[autocomplete="new-password"], input[autocomplete="current-password"], input[type="password"]',
            "username": 'input[autocomplete="username"]',
            "first_name": 'input[autocomplete="given-name"]',
            "last_name": 'input[autocomplete="family-name"]',
        }
        selector = auto_map.get(field_type)
        if selector:
            return page.query_selector(selector)
        return None

    @classmethod
    def find(cls, page: Page, field_type: str) -> Optional[ElementHandle]:
        """Try all advanced strategies in order of reliability."""
        strategies = [
            cls.find_by_autocomplete,
            cls.find_by_aria_label,
            cls.find_by_placeholder,
            cls.find_by_inputmode,
            cls.find_by_surrounding_text,
        ]

        for strategy in strategies:
            el = strategy(page, field_type)
            if el and el.is_visible():
                print(f"[AdvancedFieldFinder] Found {field_type} via {strategy.__name__}")
                return el

        return None


class ShadowDOMPenetrator:
    """Handle fields inside Shadow DOM (common in modern web components)."""

    @staticmethod
    def query_shadow_dom(page: Page, host_selector: str, inner_selector: str) -> Optional[ElementHandle]:
        """Query inside a shadow root."""
        return page.evaluate(f"""
            () => {{
                const host = document.querySelector('{host_selector}');
                if (!host || !host.shadowRoot) return null;
                return host.shadowRoot.querySelector('{inner_selector}');
            }}
        """)

    @staticmethod
    def find_all_shadow_inputs(page: Page) -> List[Dict]:
        """Recursively find all inputs inside shadow DOMs."""
        return page.evaluate("""
            () => {
                function findInputs(root, path = '') {
                    let results = [];
                    const inputs = root.querySelectorAll('input, textarea, select');
                    inputs.forEach((el, i) => {
                        results.push({
                            tag: el.tagName,
                            type: el.type,
                            name: el.name,
                            id: el.id,
                            placeholder: el.placeholder,
                            path: path + ' > ' + (el.id || el.name || el.className || 'input[' + i + ']'),
                        });
                    });
                    const hosts = root.querySelectorAll('*');
                    hosts.forEach((host, i) => {
                        if (host.shadowRoot) {
                            results = results.concat(findInputs(host.shadowRoot, path + ' > ' + (host.id || host.tagName + '[' + i + ']')));
                        }
                    });
                    return results;
                }
                return findInputs(document);
            }
        """)
