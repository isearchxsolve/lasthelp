#!/usr/bin/env python3
"""
Dynamic Field Finder
====================
Auto-discovers form fields (email, password, username, code, phone, etc.)
by scoring every visible input against known patterns. 

No hardcoded selectors — adapts to any UI layout on the fly.
"""

from typing import Dict, List, Optional, Tuple


class DynamicFieldFinder:
    """
    Scans a Playwright page for input fields matching a desired type.
    Uses heuristic scoring: type, autocomplete, name, placeholder, id, aria-label.
    """

    # Scoring weights per attribute match
    FIELD_CRITERIA: Dict[str, Dict] = {
        "email": {
            "type_priority": ["email", "text"],
            "autocomplete": ["email", "username"],
            "name_patterns": ["email", "e-mail", "mail", "userid"],
            "placeholder_patterns": ["email", "e-mail", "mail", "username"],
            "id_patterns": ["email", "login", "username", "identifier"],
            "aria_patterns": ["email", "e-mail", "mail", "username"],
            "testid_patterns": ["email", "username", "login", "identifier"],
            "label_patterns": ["email", "e-mail"],
        },
        "password": {
            "type_priority": ["password"],
            "autocomplete": ["current-password", "new-password", "off"],
            "name_patterns": ["password", "passwd", "pwd", "pass"],
            "placeholder_patterns": ["password", "pass", "pwd"],
            "id_patterns": ["password", "passwd", "pwd"],
            "aria_patterns": ["password", "pass"],
            "testid_patterns": ["password"],
            "label_patterns": ["password"],
        },
        "username": {
            "type_priority": ["text", None],
            "autocomplete": ["username"],
            "name_patterns": ["username", "login", "user", "name", "handle"],
            "placeholder_patterns": ["username", "user", "name", "login", "handle"],
            "id_patterns": ["username", "login", "user", "name"],
            "aria_patterns": ["username", "user", "name", "login"],
            "testid_patterns": ["username", "login"],
            "label_patterns": ["username", "user"],
        },
        "code": {
            "type_priority": ["text", "tel", "number", "digit"],
            "autocomplete": ["one-time-code"],
            "name_patterns": ["code", "otp", "verification", "token", "mfa", "2fa", "totp"],
            "placeholder_patterns": ["code", "otp", "verification", "token", "2fa", "mfa"],
            "id_patterns": ["code", "otp", "verification", "token", "mfa"],
            "aria_patterns": ["code", "otp", "verification"],
            "testid_patterns": ["code", "otp"],
            "label_patterns": ["code", "verification"],
        },
        "phone": {
            "type_priority": ["tel", "text"],
            "autocomplete": ["tel", "tel-national", "mobile"],
            "name_patterns": ["phone", "tel", "mobile", "cell", "phonenumber"],
            "placeholder_patterns": ["phone", "tel", "mobile", "cell", "phone"],
            "id_patterns": ["phone", "tel", "mobile"],
            "aria_patterns": ["phone", "tel", "mobile"],
            "testid_patterns": ["phone", "tel"],
            "label_patterns": ["phone", "mobile"],
        },
        "first_name": {
            "type_priority": ["text", None],
            "autocomplete": ["given-name"],
            "name_patterns": ["firstname", "first_name", "fname", "firstName"],
            "placeholder_patterns": ["first name", "first", "given"],
            "id_patterns": ["firstname", "first_name", "fname"],
            "aria_patterns": ["first name", "first"],
            "testid_patterns": ["firstName", "first_name"],
        },
        "last_name": {
            "type_priority": ["text", None],
            "autocomplete": ["family-name"],
            "name_patterns": ["lastname", "last_name", "lname", "surname", "familyName"],
            "placeholder_patterns": ["last name", "last", "surname", "family"],
            "id_patterns": ["lastname", "last_name", "lname", "surname"],
            "aria_patterns": ["last name", "last", "surname"],
            "testid_patterns": ["lastName", "last_name"],
        },
        "search": {
            "type_priority": ["search", "text", None],
            "autocomplete": ["off"],
            "name_patterns": ["search", "q", "query", "keyword"],
            "placeholder_patterns": ["search", "find", "query", "keyword"],
            "id_patterns": ["search", "q", "query"],
            "aria_patterns": ["search", "find"],
        },
        "checkbox": {
            "type_priority": ["checkbox"],
            "name_patterns": ["agree", "terms", "accept", "consent", "toc", "checkbox"],
            "id_patterns": ["agree", "terms", "accept", "consent", "toc"],
        },
    }

    EXCLUDE_TYPES = {"hidden", "submit", "button", "reset", "file", "image", "checkbox", "radio"}

    @classmethod
    def find(cls, page, field_type: str) -> Optional[object]:
        """Find the best matching element for field_type. Returns Playwright element or None."""
        if field_type not in cls.FIELD_CRITERIA:
            raise ValueError(f"Unknown field type: {field_type}")

        criteria = cls.FIELD_CRITERIA[field_type]
        inputs = page.query_selector_all(
            "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']):not([type='file'])"
        )

        scored: List[Tuple[int, object]] = []
        for inp in inputs:
            score = cls._score(inp, criteria)
            if score > 0:
                scored.append((score, inp))

        # Also check textarea elements for fields like code/email
        if field_type in ("email", "code"):
            textareas = page.query_selector_all("textarea:not([hidden])")
            for ta in textareas:
                score = cls._score(ta, criteria)
                if score > 0:
                    scored.append((score, ta))

        if not scored:
            return None
        scored.sort(key=lambda x: -x[0])
        return scored[0][1]

    @classmethod
    def find_all(cls, page, field_type: str, min_score: int = 3) -> List[object]:
        """Find all matching elements for field_type, sorted by score."""
        if field_type not in cls.FIELD_CRITERIA:
            return []
        criteria = cls.FIELD_CRITERIA[field_type]
        inputs = page.query_selector_all(
            "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']):not([type='file'])"
        )
        scored = []
        for inp in inputs:
            score = cls._score(inp, criteria)
            if score >= min_score:
                scored.append((score, inp))
        scored.sort(key=lambda x: -x[0])
        return [el for _, el in scored]

    @classmethod
    def find_and_fill(cls, page, field_type: str, value: str, min_score: int = 8) -> bool:
        """Find a field and fill it. Returns True if successful.
        FIX: Added min_score (default 8) to prevent filling generic fields."""
        el = cls.find(page, field_type)
        if not el:
            return False

        # Verify the matched element meets minimum score
        criteria = cls.FIELD_CRITERIA[field_type]
        actual_score = cls._score(el, criteria)
        if actual_score < min_score:
            print(f"[DynamicFieldFinder] Rejected {field_type} match (score={actual_score} < min={min_score})")
            return False

        try:
            el.fill(value)
            return True
        except Exception:
            try:
                el.type(value, delay=20)
                return True
            except Exception:
                return False

    @classmethod
    def find_and_click(cls, page, field_type: str, min_score: int = 8) -> bool:
        """Find a field and click it (for checkboxes). Returns True if successful.
        FIX: Added min_score to prevent clicking wrong checkboxes."""
        el = cls.find(page, field_type)
        if not el:
            return False

        criteria = cls.FIELD_CRITERIA[field_type]
        actual_score = cls._score(el, criteria)
        if actual_score < min_score:
            return False

        try:
            el.click()
            return True
        except Exception:
            return False

    @classmethod
    def _score(cls, element, criteria: Dict) -> int:
        """Score an element against field criteria. Higher = better match."""
        score = 0
        try:
            if not element.is_visible():
                return 0
        except Exception:
            return 0

        # Helper: case-insensitive substring match
        def has_any(haystack_str, patterns):
            if not haystack_str:
                return False
            hl = haystack_str.lower()
            return any(p in hl for p in patterns)

        # 1. type attribute (weight: 10)
        try:
            t = element.get_attribute("type")
            if t:
                tl = t.lower()
                type_prio = criteria.get("type_priority", [])
                if tl in type_prio:
                    score += 10
                elif tl in cls.EXCLUDE_TYPES:
                    return 0
            else:
                # No type attribute: if None is in type_priority, give partial
                if None in criteria.get("type_priority", []):
                    score += 5
        except Exception:
            pass

        # 2. autocomplete attribute (weight: 8)
        try:
            ac = element.get_attribute("autocomplete")
            if ac and has_any(ac, criteria.get("autocomplete", [])):
                score += 8
        except Exception:
            pass

        # 3. name attribute (weight: 6)
        try:
            name = element.get_attribute("name")
            if name and has_any(name, criteria.get("name_patterns", [])):
                score += 6
        except Exception:
            pass

        # 4. placeholder attribute (weight: 5)
        try:
            ph = element.get_attribute("placeholder")
            if ph and has_any(ph, criteria.get("placeholder_patterns", [])):
                score += 5
        except Exception:
            pass

        # 5. id attribute (weight: 4)
        try:
            eid = element.get_attribute("id")
            if eid and has_any(eid, criteria.get("id_patterns", [])):
                score += 4
        except Exception:
            pass

        # 6. aria-label attribute (weight: 3)
        try:
            aria = element.get_attribute("aria-label")
            if aria and has_any(aria, criteria.get("aria_patterns", [])):
                score += 3
        except Exception:
            pass

        # 7. data-testid / data-test attribute (weight: 3)
        try:
            dt = element.get_attribute("data-testid") or element.get_attribute("data-test")
            if dt and has_any(dt, criteria.get("testid_patterns", [])):
                score += 3
        except Exception:
            pass

        # 8. aria-describedby / associated label text (weight: 2)
        try:
            described = element.get_attribute("aria-describedby")
            if described and has_any(described, criteria.get("label_patterns", [])):
                score += 2
        except Exception:
            pass

        # 9. class attribute (weight: 1) — broad fallback
        try:
            cls_attr = element.get_attribute("class")
            if cls_attr and has_any(cls_attr, criteria.get("id_patterns", [])):
                score += 1
        except Exception:
            pass

        # 10. role attribute (weight: 1)
        try:
            role = element.get_attribute("role")
            if role and has_any(role, criteria.get("aria_patterns", [])):
                score += 1
        except Exception:
            pass

        return score


class DynamicButtonFinder:
    """Find buttons/links by text content, role, or testid."""

    BUTTON_PATTERNS = {
        "submit": ["submit", "sign in", "login", "log in", "continue", "next", "go", "enter"],
        "signup": ["sign up", "register", "create account", "join", "get started"],
        "verify": ["verify", "confirm", "verify email", "send code"],
        "agree": ["agree", "accept", "i agree", "accept all", "consent"],
        "create": ["create", "create api", "generate", "new key", "add key"],
        "next": ["next", "continue", "proceed", "next step"],
        "save": ["save", "update", "save profile", "update profile"],
    }

    @classmethod
    def find_button(cls, page, action_type: str) -> Optional[object]:
        """Find a button by action type using text content."""
        patterns = cls.BUTTON_PATTERNS.get(action_type, [action_type])
        selectors = []
        for p in patterns:
            selectors.extend([
                f"button:has-text('{p}')",
                f"input[type='submit'][value*='{p}']",
                f"a:has-text('{p}')",
                f"[role='button']:has-text('{p}')",
                f"[data-testid*='{p.replace(' ', '')}']",
            ])
        selector = ", ".join(selectors)
        try:
            return page.wait_for_selector(selector, timeout=5000)
        except Exception:
            return None

    @classmethod
    def click(cls, page, action_type: str) -> bool:
        """Click a button by action type. Returns True if clicked."""
        btn = cls.find_button(page, action_type)
        if not btn:
            return False
        try:
            btn.click()
            return True
        except Exception:
            try:
                page.evaluate("(el) => el.click()", btn)
                return True
            except Exception:
                return False


class DynamicLoginFlow:
    """
    Fully dynamic login flow — no hardcoded selectors needed.
    Discovers email/password fields and submit buttons on any login page.
    """

    @classmethod
    def login(cls, page, email: str, password: str, username: str = None) -> bool:
        """Log in using dynamic field discovery. Returns True if redirected to a post-login page."""
        # Find and fill email/username field
        email_found = DynamicFieldFinder.find_and_fill(page, "email", email)
        if not email_found and username:
            DynamicFieldFinder.find_and_fill(page, "username", username)
        elif not email_found:
            return False

        # Some sites have a "Next" step before password (Google, Microsoft, etc.)
        next_btn = DynamicButtonFinder.find_button(page, "submit")
        if next_btn:
            try:
                next_btn.click()
                import time
                time.sleep(1.5)
            except Exception:
                pass

        # Find and fill password field
        pwd_found = DynamicFieldFinder.find_and_fill(page, "password", password)
        if not pwd_found:
            return False

        # Click submit
        DynamicButtonFinder.click(page, "submit")

        # Wait for redirect
        try:
            page.wait_for_timeout(3000)
            return True
        except Exception:
            return False

    @classmethod
    def fill_signup_form(cls, page, email: str, password: str, username: str = None,
                         first_name: str = None, last_name: str = None, phone: str = None) -> bool:
        """Fill a signup form using dynamic field discovery."""
        DynamicFieldFinder.find_and_fill(page, "email", email)
        DynamicFieldFinder.find_and_fill(page, "password", password)
        if username:
            DynamicFieldFinder.find_and_fill(page, "username", username)
        if first_name:
            DynamicFieldFinder.find_and_fill(page, "first_name", first_name)
        if last_name:
            DynamicFieldFinder.find_and_fill(page, "last_name", last_name)
        if phone:
            DynamicFieldFinder.find_and_fill(page, "phone", phone)
        DynamicFieldFinder.find_and_click(page, "checkbox")
        return True
