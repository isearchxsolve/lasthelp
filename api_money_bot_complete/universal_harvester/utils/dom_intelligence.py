#!/usr/bin/env python3
"""
DOM Intelligence Engine
=======================
Classifies the current page state and plans/executes actions dynamically.
Uses regex-based keyword matching so "Create Account" = Sign Up,
"Log In" = Sign In, etc.  Fields are always filled before buttons are clicked.
"""

import re
import time
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class PageState(Enum):
    COOKIE_BANNER = "cookie_banner"
    LOGIN_FORM = "login_form"
    SIGNUP_FORM = "signup_form"
    EMAIL_VERIFICATION = "email_verification"
    EMAIL_PENDING = "email_pending"
    PROFILE_FORM = "profile_form"
    CAPTCHA = "captcha"
    KYC = "kyc"
    TWO_FA = "2fa"
    DASHBOARD = "dashboard"
    API_KEYS_PAGE = "api_keys_page"
    WELCOME_ONBOARDING = "welcome_onboarding"
    ERROR = "error"
    UNKNOWN = "unknown"


class Intent(Enum):
    SIGNUP = "signup"
    SIGNIN = "signin"
    API_HARVEST = "api_harvest"


@dataclass
class DOMSnapshot:
    """Complete snapshot of the current page for analysis."""
    url: str
    title: str
    visible_text: str
    inputs: List[Dict] = field(default_factory=list)
    buttons: List[Dict] = field(default_factory=list)
    links: List[Dict] = field(default_factory=list)
    iframes: List[Dict] = field(default_factory=list)
    images: List[Dict] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)


class DOMIntelligence:
    """Analyzes DOM and decides actions."""

    # ── Regex-based classification (catches synonyms) ──
    SIGNUP_REGEX = re.compile(
        r'\b(sign\s*up|signup|register|create\s*account|join\s*now|'
        r'start\s*free|new\s*account|join|become\s*a\s*member|create\s*your\s*account|'
        r'sign\s*up\s*free|register\s*now|get\s*started\s*free|open\s*account|'
        r'create\s*account\s*free|start\s*trading|begin\s*now|get\s*access|'
        r'open\s*free\s*account|start\s*your\s*account|set\s*up\s*account|'
        r'create\s*an\s*account|open\s*your\s*account)\b',
        re.I
    )

    LOGIN_REGEX = re.compile(
        r'\b(sign\s*in|signin|log\s*in|login|already\s*have\s*an\s*account|'
        r'existing\s*user|member\s*login|account\s*login|returning\s*user|'
        r'log\s*on|sign\s*on|access\s*account|account\s*access|sign\s*into|'
        r'log\s*into|enter\s*account|access\s*your\s*account)\b',
        re.I
    )

    COOKIE_REGEX = re.compile(
        r'\b(cookie|cookies|accept\s*all|accept\s*cookies|cookie\s*consent|'
        r'allow\s*cookies|reject\s*cookies|customize\s*cookies|gdpr|privacy|'
        r'i\s*agree|agree\s*and\s*proceed|essential\s*only|manage\s*cookies|'
        r'accept\s*&\s*continue|accept\s*and\s*continue|cookie\s*settings|'
        r'consent|cookie\s*policy|we\s*use\s*cookies|allow\s*all|'
        r'cookie\s*preferences|privacy\s*settings|accept\s*and\s*close|'
        r'accept\s*essential|reject\s*all|decline|dismiss)\b',
        re.I
    )

    SUBMIT_REGEX = re.compile(
        r'\b(submit|continue|next|save|done|finish|confirm|agree|accept|'
        r'create\s*account|sign\s*up|register|join|get\s*started|log\s*in|'
        r'sign\s*in|login|verify|send|go|start|proceed|complete|claim|'
        r'create\s*account\s*&\s*claim|open\s*account|activate)\b',
        re.I
    )

    SKIP_REGEX = re.compile(
        r'\b(skip|later|remind\s*me\s*later|do\s*this\s*later|not\s*now|'
        r'continue|next|i\'ll\s*do\s*this\s*later|maybe\s*later|'
        r'set\s*up\s*later|configure\s*later)\b',
        re.I
    )

    KYC_REGEX = re.compile(
        r'\b(verify\s*identity|identity\s*verification|kyc|know\s*your\s*customer|'
        r'upload\s*document|passport|driver\'s\s*license|national\s*id|'
        r'proof\s*of\s*address|selfie|face\s*verification|digilocker|'
        r'aadhaar|pan\s*card|tax\s*id|ssn|social\s*security|'
        r'government\s*id|id\s*verification|document\s*verification)\b',
        re.I
    )

    TWO_FA_REGEX = re.compile(
        r'\b(two-factor|2fa|two\s*step|authenticator\s*app|backup\s*code|'
        r'recovery\s*code|security\s*key|passkey|sms\s*code|app\s*code|'
        r'enable\s*2fa|setup\s*2fa|protect\s*your\s*account)\b',
        re.I
    )

    API_KEY_REGEX = re.compile(
        r'\b(api\s*key|api\s*token|secret\s*key|access\s*token|client\s*id|'
        r'client\s*secret|api\s*credentials|developer\s*key|app\s*key|'
        r'private\s*key|public\s*key|generate\s*key|create\s*token|'
        r'api\s*access|credentials|auth\s*token|bearer\s*token)\b',
        re.I
    )

    DASHBOARD_REGEX = re.compile(
        r'\b(dashboard|home|overview|welcome|my\s*account|account|'
        r'profile|settings|billing|subscription|plan|portfolio|'
        r'wallet|balance|assets|trading|exchange)\b',
        re.I
    )

    ERROR_REGEX = re.compile(
        r'\b(error|something\s*went\s*wrong|unable\s*to|failed|blocked|'
        r'access\s*denied|forbidden|rate\s*limit|too\s*many\s*requests|'
        r'unauthorized|session\s*expired|try\s*again\s*later|maintenance|'
        r'not\s*available|service\s*unavailable|invalid|incorrect|'
        r'wrong\s*password|wrong\s*email|already\s*exists|taken)\b',
        re.I
    )

    EMAIL_VERIFY_REGEX = re.compile(
        r'\b(verification\s*code|enter\s*code|otp|one-time\s*password|confirm\s*code|'
        r'verify\s*email|email\s*code|security\s*code|authenticate|2-step|'
        r'two-step|authenticator\s*code|enter\s*verification|mfa\s*code)\b',
        re.I
    )

    EMAIL_PENDING_REGEX = re.compile(
        r'\b(check\s*your\s*email|verify\s*your\s*email|confirmation\s*email|email\s*sent|'
        r'click\s*the\s*link|activate\s*your\s*account|confirm\s*your\s*email|'
        r'email\s*verification|verify\s*email\s*address|we\s*sent\s*you|'
        r'please\s*verify|activation\s*required)\b',
        re.I
    )

    PROFILE_REGEX = re.compile(
        r'\b(first\s*name|last\s*name|full\s*name|date\s*of\s*birth|birthday|'
        r'gender|phone\s*number|mobile\s*number|address|city|state|'
        r'zip\s*code|postal\s*code|country|company|organization|'
        r'job\s*title|occupation|profile\s*picture|avatar|bio|'
        r'about\s*you|display\s*name|username|handle|timezone|'
        r'language|preferences|complete\s*profile|tell\s*us\s*about|'
        r'personal\s*info|contact\s*info|identity\s*info)\b',
        re.I
    )

    WELCOME_REGEX = re.compile(
        r'\b(welcome|getting\s*started|onboarding|setup|let\'s\s*get\s*started|'
        r'tell\s*us|choose\s*your|select\s*your|personalize|'
        r'customize\s*your\s*experience|welcome\s*aboard)\b',
        re.I
    )

    CAPTCHA_IFRAME_PATTERNS = [
        "recaptcha", "hcaptcha", "captcha", "challenge", "verify you",
    ]

    HUMAN_FALLBACK_STATES = {
        PageState.KYC,
        PageState.TWO_FA,
        PageState.CAPTCHA,
        PageState.UNKNOWN,
    }

    HUMAN_INSTRUCTIONS = {
        PageState.KYC: [
            "HUMAN DELEGATION: KYC / Identity Verification required.",
            "Please upload ID document or complete verification in the browser.",
            "Press Enter here when done...",
        ],
        PageState.TWO_FA: [
            "HUMAN DELEGATION: Two-Factor Authentication required.",
            "Please enter 2FA code or setup authenticator in the browser.",
            "Press Enter here when done...",
        ],
        PageState.CAPTCHA: [
            "HUMAN DELEGATION: CAPTCHA challenge detected.",
            "Please solve the CAPTCHA in the browser window.",
            "Press Enter here when done...",
        ],
        PageState.UNKNOWN: [
            "HUMAN DELEGATION: Unknown page state — bot is unsure what to do.",
            "Please navigate or interact with the page as needed.",
            "Press Enter here when done...",
        ],
    }

    def __init__(self, page):
        self.page = page
        self._last_snapshot = None

    def _log(self, msg: str):
        print(f"[DOM-Intel] {msg}")

    def _is_signup_text(self, text: str) -> bool:
        return bool(text and self.SIGNUP_REGEX.search(text))

    def _is_login_text(self, text: str) -> bool:
        return bool(text and self.LOGIN_REGEX.search(text))

    def _is_cookie_text(self, text: str) -> bool:
        return bool(text and self.COOKIE_REGEX.search(text))

    def _is_submit_text(self, text: str) -> bool:
        return bool(text and self.SUBMIT_REGEX.search(text))

    def _is_skip_text(self, text: str) -> bool:
        return bool(text and self.SKIP_REGEX.search(text))

    def _is_kyc_text(self, text: str) -> bool:
        return bool(text and self.KYC_REGEX.search(text))

    def _is_2fa_text(self, text: str) -> bool:
        return bool(text and self.TWO_FA_REGEX.search(text))

    def _is_api_key_text(self, text: str) -> bool:
        return bool(text and self.API_KEY_REGEX.search(text))

    def _is_dashboard_text(self, text: str) -> bool:
        return bool(text and self.DASHBOARD_REGEX.search(text))

    def _is_error_text(self, text: str) -> bool:
        return bool(text and self.ERROR_REGEX.search(text))

    def _is_email_verify_text(self, text: str) -> bool:
        return bool(text and self.EMAIL_VERIFY_REGEX.search(text))

    def _is_email_pending_text(self, text: str) -> bool:
        return bool(text and self.EMAIL_PENDING_REGEX.search(text))

    def _is_profile_text(self, text: str) -> bool:
        return bool(text and self.PROFILE_REGEX.search(text))

    def _is_welcome_text(self, text: str) -> bool:
        return bool(text and self.WELCOME_REGEX.search(text))

    def capture(self) -> DOMSnapshot:
        js = """
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 &&
                       window.getComputedStyle(el).display !== 'none' &&
                       window.getComputedStyle(el).visibility !== 'hidden';
            };
            const text = (el) => (el.innerText || el.textContent || '').trim();
            const inputs = Array.from(document.querySelectorAll('input, select, textarea'))
                .filter(visible)
                .map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute('type') || el.tagName.toLowerCase(),
                    name: el.getAttribute('name') || '',
                    id: el.getAttribute('id') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    autocomplete: el.getAttribute('autocomplete') || '',
                    className: el.className || '',
                    value: el.value || '',
                    labelText: (() => {
                        const id = el.getAttribute('id');
                        if (id) {
                            const lbl = document.querySelector(`label[for="${CSS.escape(id)}"]`);
                            if (lbl) return text(lbl);
                        }
                        const parent = el.closest('label');
                        if (parent) return text(parent);
                        let prev = el.previousElementSibling;
                        while (prev) {
                            const t = text(prev);
                            if (t) return t;
                            prev = prev.previousElementSibling;
                        }
                        return '';
                    })()
                }));
            const buttons = Array.from(document.querySelectorAll('button, a[role="button"], input[type="submit"], [class*="btn"], [class*="button"]'))
                .filter(visible)
                .map(el => ({
                    tag: el.tagName.toLowerCase(),
                    text: text(el).slice(0, 100),
                    ariaLabel: el.getAttribute('aria-label') || '',
                    className: el.className || '',
                    href: el.getAttribute('href') || '',
                }));
            const links = Array.from(document.querySelectorAll('a'))
                .filter(visible)
                .map(el => ({
                    text: text(el).slice(0, 100),
                    href: el.getAttribute('href') || '',
                }));
            const iframes = Array.from(document.querySelectorAll('iframe'))
                .map(el => ({
                    src: el.getAttribute('src') || '',
                    title: el.getAttribute('title') || '',
                }));
            const images = Array.from(document.querySelectorAll('img'))
                .filter(visible)
                .map(el => ({
                    alt: el.getAttribute('alt') || '',
                    src: el.getAttribute('src') || '',
                }));
            const bodyText = text(document.body).slice(0, 5000).toLowerCase();
            const alerts = Array.from(document.querySelectorAll('[role="alert"], .alert, .error, .notification, [class*="error"], [class*="alert"]'))
                .filter(visible)
                .map(el => text(el).slice(0, 200));
            return {
                url: window.location.href,
                title: document.title,
                visibleText: bodyText,
                inputs: inputs,
                buttons: buttons,
                links: links,
                iframes: iframes,
                images: images,
                alerts: alerts,
            };
        }
        """
        data = self.page.evaluate(js)
        snap = DOMSnapshot(
            url=data["url"],
            title=data["title"],
            visible_text=data["visibleText"],
            inputs=data["inputs"],
            buttons=data["buttons"],
            links=data["links"],
            iframes=data["iframes"],
            images=data["images"],
            alerts=data["alerts"],
        )
        self._last_snapshot = snap
        return snap

    def classify(self, snap: DOMSnapshot = None) -> PageState:
        snap = snap or self.capture()
        scores = {state: 0 for state in PageState}
        text = snap.visible_text
        url = snap.url.lower()
        title = snap.title.lower()

        all_button_text = " ".join(b["text"].lower() for b in snap.buttons if b.get("text"))
        all_link_text = " ".join(l["text"].lower() for l in snap.links if l.get("text"))
        all_input_text = " ".join(
            (i.get("labelText","") + " " + i.get("placeholder","") + " " + i.get("name","") + " " + 
             i.get("id","") + " " + i.get("ariaLabel","")).lower()
            for i in snap.inputs
        )
        combined_text = text + " " + all_button_text + " " + all_link_text + " " + all_input_text

        signup_btn_count = sum(1 for b in snap.buttons if self._is_signup_text(b.get("text", "")))
        login_btn_count = sum(1 for b in snap.buttons if self._is_login_text(b.get("text", "")))
        cookie_btn_count = sum(1 for b in snap.buttons if self._is_cookie_text(b.get("text", "")))

        if cookie_btn_count > 0 or self._is_cookie_text(combined_text):
            scores[PageState.COOKIE_BANNER] += 10 + cookie_btn_count * 3

        captcha_iframes = [f for f in snap.iframes if any(p in (f.get("src","")+f.get("title","")).lower() for p in self.CAPTCHA_IFRAME_PATTERNS)]
        if captcha_iframes:
            scores[PageState.CAPTCHA] += 15 + len(captcha_iframes) * 5
        if any(k in combined_text for k in ["i'm not a robot", "verify you are human", "challenge", "select all images"]):
            scores[PageState.CAPTCHA] += 10
        if self.page.query_selector(".g-recaptcha, .h-captcha, [class*='captcha'], [id*='captcha']"):
            scores[PageState.CAPTCHA] += 8

        if self._is_error_text(combined_text) or snap.alerts:
            scores[PageState.ERROR] += 6 + len(snap.alerts) * 2

        if self._is_dashboard_text(combined_text):
            scores[PageState.DASHBOARD] += 4
        if "dashboard" in url or "home" in url or (url.count("/") <= 3 and "login" not in url and "signup" not in url):
            scores[PageState.DASHBOARD] += 2
        no_auth_buttons = signup_btn_count == 0 and login_btn_count == 0
        no_auth_fields = not any(i["type"] in ("email", "password") for i in snap.inputs)
        if no_auth_buttons and no_auth_fields and self._is_dashboard_text(combined_text):
            scores[PageState.DASHBOARD] += 6

        if self._is_api_key_text(combined_text):
            scores[PageState.API_KEYS_PAGE] += 8
        if "api" in url and any(k in url for k in ["key", "token", "credential", "developer", "app"]):
            scores[PageState.API_KEYS_PAGE] += 5
        if any(k in title for k in ["api", "developer", "keys", "tokens"]):
            scores[PageState.API_KEYS_PAGE] += 3

        if signup_btn_count > 0:
            scores[PageState.SIGNUP_FORM] += 8 + signup_btn_count * 3
        if self._is_signup_text(combined_text):
            scores[PageState.SIGNUP_FORM] += 5
        if "signup" in url or "register" in url or "join" in url:
            scores[PageState.SIGNUP_FORM] += 4
        has_email = any(i["type"] == "email" for i in snap.inputs)
        has_password = any(i["type"] == "password" for i in snap.inputs)
        if has_email and has_password:
            scores[PageState.SIGNUP_FORM] += 3
        elif has_email:
            scores[PageState.SIGNUP_FORM] += 1
        if any(k in combined_text for k in ["agree to terms", "terms of service", "privacy policy", "i accept", "create password"]):
            scores[PageState.SIGNUP_FORM] += 2

        if login_btn_count > 0:
            scores[PageState.LOGIN_FORM] += 8 + login_btn_count * 3
        if self._is_login_text(combined_text):
            scores[PageState.LOGIN_FORM] += 5
        if "login" in url or "signin" in url:
            scores[PageState.LOGIN_FORM] += 4
        if has_email and has_password:
            scores[PageState.LOGIN_FORM] += 3
        elif has_email:
            scores[PageState.LOGIN_FORM] += 1

        code_inputs = [i for i in snap.inputs if i["type"] in ("tel", "text", "number") and
                       any(k in (i.get("labelText","")+i.get("placeholder","")+i.get("name","")+i.get("id","")+i.get("ariaLabel","")).lower()
                       for k in ["code", "otp", "verification", "token", "pin", "2fa", "mfa"])]
        if code_inputs:
            scores[PageState.EMAIL_VERIFICATION] += 12 + len(code_inputs) * 4
        if self._is_email_verify_text(combined_text):
            scores[PageState.EMAIL_VERIFICATION] += 6

        if self._is_email_pending_text(combined_text):
            scores[PageState.EMAIL_PENDING] += 10

        if self._is_2fa_text(combined_text):
            scores[PageState.TWO_FA] += 8

        if self._is_kyc_text(combined_text):
            scores[PageState.KYC] += 10
        if any(k in combined_text for k in ["upload", "document", "scan", "selfie", "photo id"]):
            scores[PageState.KYC] += 4

        profile_fields = [i for i in snap.inputs if
                          (i["type"] in ("text", None) and any(k in (i.get("labelText","")+i.get("placeholder","")+i.get("name","")+i.get("id","")+i.get("ariaLabel","")).lower()
                           for k in ["first name", "last name", "gender", "birth", "phone", "address", "city", "country", "zip", "postal", "state", "company", "website"]))]
        if profile_fields:
            scores[PageState.PROFILE_FORM] += 8 + len(profile_fields) * 2
        if self._is_profile_text(combined_text):
            scores[PageState.PROFILE_FORM] += 4

        if self._is_welcome_text(combined_text):
            scores[PageState.WELCOME_ONBOARDING] += 6

        if scores[PageState.LOGIN_FORM] > 0 and scores[PageState.SIGNUP_FORM] > 0:
            if "login" in url or "signin" in url:
                scores[PageState.SIGNUP_FORM] -= 5
            elif "signup" in url or "register" in url:
                scores[PageState.LOGIN_FORM] -= 5
            if login_btn_count > signup_btn_count:
                scores[PageState.SIGNUP_FORM] -= 3
            elif signup_btn_count > login_btn_count:
                scores[PageState.LOGIN_FORM] -= 3

        captcha_score = scores[PageState.CAPTCHA]
        form_score = scores[PageState.LOGIN_FORM] + scores[PageState.SIGNUP_FORM]
        if captcha_score >= 10 and form_score >= 10:
            scores[PageState.CAPTCHA] = max(0, captcha_score - form_score)
        if captcha_iframes and not any(k in combined_text for k in ["i'm not a robot", "verify you are human", "select all images"]):
            scores[PageState.CAPTCHA] = max(0, scores[PageState.CAPTCHA] - 10)

        best_state = max(scores, key=scores.get)
        best_score = scores[best_state]
        if best_score < 3:
            best_state = PageState.UNKNOWN

        top3 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        self._log(f"Classification scores: {[(s.value, v) for s, v in top3]}")
        self._log(f"Winner: {best_state.value} (score={best_score})")

        return best_state

    def plan_action(self, intent: Intent, state: PageState, snap: DOMSnapshot = None) -> Dict[str, Any]:
        snap = snap or self._last_snapshot
        action = {"type": "none", "reason": f"State={state.value}, Intent={intent.value}"}

        has_any_inputs = len(snap.inputs) > 0
        has_email_field = any(i["type"] == "email" for i in snap.inputs)
        has_password_field = any(i["type"] == "password" for i in snap.inputs)
        has_text_fields = any(i["type"] in ("text", "email", "password", "tel", "number") for i in snap.inputs)
        has_code_field = any(i["type"] in ("tel", "text", "number") and
                             any(k in (i.get("labelText","")+i.get("placeholder","")+i.get("name","")+i.get("id","")+i.get("ariaLabel","")).lower()
                             for k in ["code", "otp", "verification", "token", "pin", "2fa", "mfa"])
                             for i in snap.inputs)
        has_buttons = len(snap.buttons) > 0

        signup_btns = [b for b in snap.buttons if self._is_signup_text(b.get("text", ""))]
        login_btns = [b for b in snap.buttons if self._is_login_text(b.get("text", ""))]
        submit_btns = [b for b in snap.buttons if self._is_submit_text(b.get("text", ""))]
        skip_btns = [b for b in snap.buttons if self._is_skip_text(b.get("text", ""))]

        self._log(f"Elements: any_inputs={has_any_inputs}, email={has_email_field}, pwd={has_password_field}, "
                   f"text_fields={has_text_fields}, code={has_code_field}, buttons={has_buttons}, "
                   f"signup_btns={len(signup_btns)}, login_btns={len(login_btns)}, "
                   f"submit_btns={len(submit_btns)}, skip_btns={len(skip_btns)}")

        if state == PageState.COOKIE_BANNER:
            action = {"type": "accept_cookie", "reason": "Cookie consent banner detected"}

        elif state == PageState.CAPTCHA:
            action = {"type": "solve_captcha", "reason": "CAPTCHA detected"}

        elif state == PageState.ERROR:
            action = {"type": "abort", "reason": f"Error page detected: {snap.alerts[:3] if snap else 'unknown'}"}

        elif state == PageState.EMAIL_VERIFICATION:
            if has_code_field:
                action = {"type": "enter_email_code", "reason": "Email verification code input visible"}
            elif has_buttons:
                action = {"type": "click_skip", "reason": "No code field — clicking skip/resend"}
            else:
                action = {"type": "wait_or_skip_email", "reason": "Email verification pending — waiting"}

        elif state == PageState.EMAIL_PENDING:
            if has_buttons:
                action = {"type": "click_skip", "reason": "Email pending — clicking skip/continue"}
            else:
                action = {"type": "wait_or_skip_email", "reason": "Email verification pending — waiting"}

        elif state == PageState.PROFILE_FORM:
            if has_any_inputs:
                action = {"type": "fill_profile", "reason": "Profile completion form detected"}
            elif has_buttons:
                action = {"type": "click_skip", "reason": "Profile page with no fields — clicking skip/continue"}
            else:
                action = {"type": "explore", "reason": "Profile page with no interactive elements", "intent": intent.value}

        elif state == PageState.KYC:
            if has_buttons:
                action = {"type": "skip_or_handle_kyc", "reason": "KYC detected — Stage 1: attempt skip"}
            else:
                action = {"type": "human_delegation", "reason": "KYC with no skip button — human required"}

        elif state == PageState.TWO_FA:
            if has_code_field:
                action = {"type": "enter_email_code", "reason": "2FA code input visible"}
            elif has_buttons:
                action = {"type": "skip_2fa", "reason": "2FA detected — attempting skip"}
            else:
                action = {"type": "human_delegation", "reason": "2FA with no skip option — human required"}

        elif state == PageState.WELCOME_ONBOARDING:
            if has_buttons:
                action = {"type": "complete_onboarding", "reason": "Welcome/onboarding wizard detected"}
            else:
                action = {"type": "explore", "reason": "Onboarding with no buttons", "intent": intent.value}

        elif state == PageState.API_KEYS_PAGE:
            action = {"type": "extract_keys", "reason": "API keys page detected"}

        elif state == PageState.DASHBOARD and intent in (Intent.SIGNUP, Intent.SIGNIN):
            action = {"type": "success", "reason": "Reached dashboard — intent achieved"}

        elif intent == Intent.SIGNUP:
            if state == PageState.LOGIN_FORM:
                if signup_btns:
                    action = {"type": "click_signup_button", "reason": "On login page, found signup button"}
                else:
                    action = {"type": "fill_form", "form_type": "signup", "reason": "Login form but treating as signup"}
            elif state == PageState.SIGNUP_FORM:
                if has_any_inputs:
                    action = {"type": "fill_form", "form_type": "signup", "reason": "Signup form with inputs detected — filling first"}
                elif signup_btns:
                    action = {"type": "click_signup_button", "reason": "Signup page with buttons but no inputs — clicking"}
                elif has_buttons:
                    action = {"type": "click_any_button", "reason": "Signup page with generic buttons — clicking"}
                else:
                    action = {"type": "explore", "reason": "Signup page with no interactive elements", "intent": intent.value}
            elif state == PageState.UNKNOWN:
                if has_any_inputs:
                    action = {"type": "fill_form", "form_type": "signup", "reason": "Unknown state but inputs found — filling"}
                elif signup_btns:
                    action = {"type": "click_signup_button", "reason": "Unknown state but signup button found"}
                else:
                    action = {"type": "explore", "reason": "Unknown state — exploring", "intent": intent.value}

        elif intent == Intent.SIGNIN:
            if state == PageState.SIGNUP_FORM:
                if login_btns:
                    action = {"type": "click_login_button", "reason": "On signup page, found login button"}
                else:
                    action = {"type": "fill_form", "form_type": "login", "reason": "Signup form but treating as login"}
            elif state == PageState.LOGIN_FORM:
                if has_any_inputs:
                    action = {"type": "fill_form", "form_type": "login", "reason": "Login form with inputs detected — filling first"}
                elif login_btns:
                    action = {"type": "click_login_button", "reason": "Login page with buttons but no inputs — clicking"}
                elif has_buttons:
                    action = {"type": "click_any_button", "reason": "Login page with generic buttons — clicking"}
                else:
                    action = {"type": "explore", "reason": "Login page with no interactive elements", "intent": intent.value}
            elif state == PageState.UNKNOWN:
                if has_any_inputs:
                    action = {"type": "fill_form", "form_type": "login", "reason": "Unknown state but inputs found — filling"}
                elif login_btns:
                    action = {"type": "click_login_button", "reason": "Unknown state but login button found"}
                else:
                    action = {"type": "explore", "reason": "Unknown state — exploring", "intent": intent.value}

        elif intent == Intent.API_HARVEST:
            if state == PageState.API_KEYS_PAGE:
                action = {"type": "extract_keys", "reason": "API keys page detected"}
            elif state == PageState.LOGIN_FORM or state == PageState.SIGNUP_FORM:
                action = {"type": "delegate_signin", "reason": "Need to sign in before harvesting"}
            elif state == PageState.DASHBOARD:
                action = {"type": "navigate_to_api", "reason": "On dashboard — navigating to API page"}
            elif state == PageState.UNKNOWN:
                action = {"type": "explore", "reason": "Unknown state — exploring", "intent": intent.value}

        self._log(f"Planned action: {action['type']} | {action.get('reason', '')}")
        return action

    def execute_action(self, action: Dict, credentials: Dict = None, email_platform: str = "", verifier = None) -> bool:
        atype = action["type"]
        reason = action.get("reason", "")
        print(f"[DOM-Intel] Action: {atype} | {reason}")

        if atype == "none":
            return False

        if atype == "accept_cookie":
            return self._accept_cookie()

        if atype == "solve_captcha":
            return False

        if atype == "fill_form":
            form_type = action.get("form_type", "signup")
            return self._fill_auth_form(form_type, credentials)

        if atype == "click_link":
            text = action.get("text", "")
            try:
                el = self.page.get_by_text(text, exact=False).first
                if el and el.is_visible():
                    el.click()
                    return True
            except:
                pass
            href = action.get("selector", "")
            if href:
                try:
                    el = self.page.locator(href).first
                    if el and el.is_visible():
                        el.click()
                        return True
                except:
                    pass
            return False

        if atype == "enter_email_code":
            return self._enter_email_code(email_platform, verifier)

        if atype == "wait_or_skip_email":
            return self._skip_or_wait_email()

        if atype == "fill_profile":
            return self._fill_profile_form()

        if atype == "skip_or_handle_kyc":
            return self._skip_kyc()

        if atype == "skip_2fa":
            return self._skip_2fa()

        if atype == "complete_onboarding":
            return self._complete_onboarding()

        if atype == "click_signup_button":
            return self._click_signup_button(credentials)

        if atype == "click_login_button":
            return self._click_login_button(credentials)

        if atype == "click_any_button":
            return self._click_any_button()

        if atype == "click_skip":
            return self._click_skip_button()

        if atype == "human_delegation":
            return self._delegate_to_human(PageState.UNKNOWN)

        if atype == "explore":
            intent_val = action.get("intent")
            intent_enum = None
            if intent_val:
                try:
                    intent_enum = Intent(intent_val)
                except:
                    pass
            return self._explore_page(intent_enum, credentials)

        if atype == "navigate_to_api":
            return True

        if atype == "success":
            return True

        if atype == "abort":
            return False

        return False

    def wait_for_dom_change(self, timeout_seconds: int = 300, poll_interval: float = 2.0) -> Tuple[bool, PageState]:
        import hashlib
        initial_snap = self.capture()
        initial_hash = hashlib.md5(str(initial_snap.visible_text).encode()).hexdigest()
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            time.sleep(poll_interval)
            try:
                snap = self.capture()
                new_hash = hashlib.md5(str(snap.visible_text).encode()).hexdigest()
                if new_hash != initial_hash:
                    new_state = self.classify(snap)
                    return True, new_state
            except Exception as e:
                self._log(f"Poll error during wait: {e}")
        current_snap = self.capture()
        current_state = self.classify(current_snap)
        return False, current_state

    def _click_signup_button(self, credentials: Dict = None) -> bool:
        snap = self.capture()

        has_auth_inputs = any(
            i["type"] in ("email", "text", "tel", "password") or 
            any(k in (i.get("placeholder","")+i.get("labelText","")).lower() 
                for k in ["email", "phone", "mobile", "password", "account"])
            for i in snap.inputs
        )
        if has_auth_inputs and credentials:
            print("[DOM-Intel] Safety: filling auth inputs before clicking signup button...")
            self._fill_auth_form("signup", credentials)
            self.page.wait_for_timeout(500)

        for role in ["button", "link"]:
            try:
                el = self.page.get_by_role(role, name=self.SIGNUP_REGEX).first
                if el and el.is_visible():
                    el.click()
                    print(f"[DOM-Intel] Clicked signup {role} by regex")
                    return True
            except:
                pass

        for btn in snap.buttons:
            txt = btn.get("text", "")
            if self._is_signup_text(txt):
                try:
                    el = self.page.get_by_text(txt, exact=False).first
                    if el and el.is_visible():
                        el.click()
                        print(f"[DOM-Intel] Clicked signup button: '{txt[:50]}'")
                        return True
                except:
                    pass

        return self._click_any_button()

    def _click_login_button(self, credentials: Dict = None) -> bool:
        snap = self.capture()

        has_auth_inputs = any(
            i["type"] in ("email", "text", "tel", "password") or 
            any(k in (i.get("placeholder","")+i.get("labelText","")).lower() 
                for k in ["email", "phone", "mobile", "password", "account"])
            for i in snap.inputs
        )
        if has_auth_inputs and credentials:
            print("[DOM-Intel] Safety: filling auth inputs before clicking login button...")
            self._fill_auth_form("login", credentials)
            self.page.wait_for_timeout(500)

        for role in ["button", "link"]:
            try:
                el = self.page.get_by_role(role, name=self.LOGIN_REGEX).first
                if el and el.is_visible():
                    el.click()
                    print(f"[DOM-Intel] Clicked login {role} by regex")
                    return True
            except:
                pass

        for btn in snap.buttons:
            txt = btn.get("text", "")
            if self._is_login_text(txt):
                try:
                    el = self.page.get_by_text(txt, exact=False).first
                    if el and el.is_visible():
                        el.click()
                        print(f"[DOM-Intel] Clicked login button: '{txt[:50]}'")
                        return True
                except:
                    pass

        return self._click_any_button()

    def _accept_cookie(self) -> bool:
        accept_keywords = ["accept all", "accept", "agree", "allow all", "allow cookies", "i agree", "got it", "ok", "yes", "continue", "essential only", "reject", "decline", "dismiss"]
        for kw in accept_keywords:
            try:
                btn = self.page.get_by_role("button", name=re.compile(kw, re.I)).first
                if btn and btn.is_visible():
                    btn.click()
                    print(f"[DOM-Intel] Clicked cookie button: '{kw}'")
                    self.page.wait_for_timeout(500)
                    return True
            except:
                pass
        try:
            btns = self.page.query_selector_all("button")
            for b in btns:
                text = b.inner_text().strip().lower()
                if any(k in text for k in accept_keywords[:5]):
                    b.click()
                    print(f"[DOM-Intel] Clicked cookie button (fallback): '{text}'")
                    return True
        except:
            pass
        try:
            self.page.keyboard.press("Escape")
            print("[DOM-Intel] Pressed Escape to dismiss cookie banner")
            self.page.wait_for_timeout(500)
            return True
        except:
            pass
        return False

    def _fill_auth_form(self, form_type: str, credentials: Dict) -> bool:
        from utils.smart_field_detector import SmartFieldDetector
        from utils.dynamic_selector import DynamicButtonFinder, DynamicFieldFinder

        if not credentials:
            print("[DOM-Intel] No credentials provided")
            return False

        snap = self.capture()
        values = {}
        if form_type == "signup":
            values = {
                "email": credentials.get("email", ""),
                "password": credentials.get("password", ""),
                "username": credentials.get("username", ""),
                "first_name": credentials.get("first_name", "Money"),
                "last_name": credentials.get("last_name", "Bot"),
            }
        else:
            values = {
                "email": credentials.get("email", ""),
                "password": credentials.get("password", ""),
                "username": credentials.get("username", ""),
            }

        # Phase 1: SmartFieldDetector (label-based, 7 selector strategies)
        filled = SmartFieldDetector.fill_all(self.page, values)
        filled_count = sum(1 for v in filled.values() if v)
        print(f"[DOM-Intel] SmartFieldDetector filled {filled_count} fields")

        # Phase 2: DynamicFieldFinder fallback — ONLY for email and password
        # FIX: Do NOT use DynamicFieldFinder for first_name/last_name/username
        # because it fills generic text inputs with wrong values like "Bot"
        essential_fields = ["email", "password"]
        for field_type in essential_fields:
            if values.get(field_type) and not filled.get(field_type):
                if DynamicFieldFinder.find_and_fill(self.page, field_type, values[field_type], min_score=8):
                    filled[field_type] = True
                    filled_count += 1
                    print(f"[DOM-Intel] DynamicFieldFinder filled {field_type}")

        # Phase 3: Check for terms checkboxes (broadened keywords)
        try:
            checkboxes = self.page.query_selector_all("input[type='checkbox']")
            for cb in checkboxes:
                label = ""
                cb_id = cb.get_attribute("id")
                if cb_id:
                    lbl = self.page.query_selector(f"label[for='{cb_id}']")
                    if lbl:
                        label = lbl.inner_text().lower()
                if not label:
                    parent = cb.evaluate("el => el.closest('label') ? el.closest('label').innerText : ''")
                    label = (parent or "").lower()
                # FIX: Broader checkbox detection including "read and agree"
                checkbox_keywords = [
                    "agree", "terms", "accept", "consent", "privacy", 
                    "i confirm", "i have read", "i agree", "read and agree",
                    "i accept", "i have read and agree"
                ]
                if any(k in label for k in checkbox_keywords):
                    if not cb.is_checked():
                        cb.click()
                        print(f"[DOM-Intel] Checked terms checkbox: '{label[:50]}'")
        except Exception:
            pass

        # Phase 4: Click submit via regex
        submitted = False

        print(f"[DOM-Intel] Attempting to click submit button for {form_type} form...")
        
        # Try submit button patterns first
        if form_type == "signup":
            submitted = DynamicButtonFinder.click(self.page, "signup")
            print(f"[DOM-Intel] DynamicButtonFinder.click('signup') returned: {submitted}")
        else:
            submitted = DynamicButtonFinder.click(self.page, "submit")
            print(f"[DOM-Intel] DynamicButtonFinder.click('submit') returned: {submitted}")

        if not submitted:
            submitted = DynamicButtonFinder.click(self.page, "submit" if form_type == "signup" else "signup")
            print(f"[DOM-Intel] DynamicButtonFinder.click(fallback) returned: {submitted}")

        if not submitted:
            btns = self.page.query_selector_all("button, input[type='submit'], a[role='button']")
            for b in btns:
                try:
                    t = b.inner_text().strip().lower()
                    if self._is_submit_text(t):
                        print(f"[DOM-Intel] Found submit button via text: '{t[:50]}'")
                        b.click()
                        submitted = True
                        print(f"[DOM-Intel] Clicked submit button: '{t[:50]}'")
                        break
                except:
                    pass

        if not submitted:
            for btn in snap.buttons:
                txt = btn.get("text", "").strip().lower()
                if self._is_submit_text(txt):
                    try:
                        el = self.page.get_by_text(txt, exact=False).first
                        if el and el.is_visible():
                            el.click()
                            print(f"[DOM-Intel] Clicked snapshot submit: '{txt[:50]}'")
                            submitted = True
                            break
                    except:
                        pass

        if not submitted:
            btns = self.page.query_selector_all("button")
            for b in btns:
                try:
                    if b.is_visible():
                        t = b.inner_text().strip()
                        print(f"[DOM-Intel] Clicking generic button as last resort: '{t[:50]}'")
                        b.click()
                        submitted = True
                        break
                except:
                    pass

        # Check if we're still on the same page after attempting submission
        try:
            current_url = self.page.url
            if "signup" in current_url or "register" in current_url:
                # If we're still on the signup page, the form wasn't submitted
                print(f"[DOM-Intel] Form submission failed: Still on signup page (URL: {current_url})")
                return False
        except:
            pass
        
        # Return True ONLY if form was actually submitted (button clicked and page navigated)
        print(f"[DOM-Intel] Form submission result: {submitted}")
        return submitted

    def _enter_email_code(self, platform: str, verifier) -> bool:
        from utils.dynamic_selector import DynamicFieldFinder
        print(f"[DOM-Intel] Fetching email code for {platform}...")
        if verifier:
            result = verifier.wait_for_verification(
                sender_keywords=[platform],
                timeout_seconds=120
            )
            if result and result.get("code"):
                code = result["code"]
                print(f"[DOM-Intel] Got code: {code}")
                if DynamicFieldFinder.find_and_fill(self.page, "code", code):
                    from utils.dynamic_selector import DynamicButtonFinder
                    DynamicButtonFinder.click(self.page, "submit")
                    return True
        print("[DOM-Intel] No code received — looking for skip button...")
        return self._click_skip_button()

    def _skip_or_wait_email(self) -> bool:
        print("[DOM-Intel] Email verification pending — waiting 10s then looking for skip...")
        self.page.wait_for_timeout(10000)
        return self._click_skip_button()

    def _fill_profile_form(self) -> bool:
        from utils.smart_field_detector import SmartFieldDetector
        from utils.dynamic_selector import DynamicButtonFinder
        import random

        values = {
            "first_name": "Money",
            "last_name": "Bot",
            "full_name": "Money Bot",
            "phone": f"555{random.randint(1000000, 9999999)}",
            "country": "United States",
            "city": "New York",
            "state": "NY",
            "zip": "10001",
            "address": "123 Wall Street",
            "company": "MoneyBot Inc.",
            "website": "https://moneybot.ai",
        }
        filled = SmartFieldDetector.fill_all(self.page, values)
        filled_count = sum(1 for v in filled.values() if v)
        print(f"[DOM-Intel] Profile filled {filled_count} fields")
        try:
            selects = self.page.query_selector_all("select")
            for s in selects:
                try:
                    s.select_option(index=1)
                except:
                    pass
        except:
            pass
        DynamicButtonFinder.click(self.page, "save")
        DynamicButtonFinder.click(self.page, "next")
        DynamicButtonFinder.click(self.page, "submit")
        return filled_count > 0

    def _skip_kyc(self) -> bool:
        print("[DOM-Intel] KYC detected — attempting skip...")
        skip_texts = ["skip", "later", "remind me later", "do this later", "not now", "continue without", "maybe later"]
        for text in skip_texts:
            try:
                el = self.page.get_by_text(text, exact=False).first
                if el and el.is_visible():
                    el.click()
                    print(f"[DOM-Intel] Clicked KYC skip: '{text}'")
                    return True
            except:
                pass
        return False

    def _skip_2fa(self) -> bool:
        print("[DOM-Intel] 2FA setup detected — attempting skip...")
        return self._click_skip_button()

    def _complete_onboarding(self) -> bool:
        print("[DOM-Intel] Onboarding wizard — clicking through...")
        from utils.dynamic_selector import DynamicButtonFinder
        for action in ["next", "continue", "get started", "skip", "done", "finish"]:
            if DynamicButtonFinder.click(self.page, action):
                self.page.wait_for_timeout(1500)
                return True
        return False

    def _explore_page(self, intent: Intent = None, credentials: Dict = None) -> bool:
        print("[DOM-Intel] Exploring page aggressively...")
        snap = self.capture()

        email_inputs = [i for i in snap.inputs if i["type"] == "email"]
        pwd_inputs = [i for i in snap.inputs if i["type"] == "password"]
        text_inputs = [i for i in snap.inputs if i["type"] in ("text", "email")]

        if email_inputs or pwd_inputs or text_inputs:
            print(f"[DOM-Intel] Found auth inputs: {len(email_inputs)} email, {len(pwd_inputs)} password, {len(text_inputs)} text")
            if intent and intent in (Intent.SIGNUP, Intent.SIGNIN):
                creds = credentials or getattr(self, '_credentials', None) or {}
                return self._fill_auth_form(
                    "signup" if intent == Intent.SIGNUP else "login",
                    creds
                )
            return True

        if intent == Intent.SIGNUP:
            for btn in snap.buttons:
                txt = btn.get("text", "").lower()
                if self._is_signup_text(txt):
                    try:
                        el = self.page.get_by_text(btn["text"], exact=False).first
                        if el and el.is_visible():
                            el.click()
                            print(f"[DOM-Intel] Clicked signup button: '{btn['text']}'")
                            return True
                    except:
                        pass

        if intent == Intent.SIGNIN:
            for btn in snap.buttons:
                txt = btn.get("text", "").lower()
                if self._is_login_text(txt):
                    try:
                        el = self.page.get_by_text(btn["text"], exact=False).first
                        if el and el.is_visible():
                            el.click()
                            print(f"[DOM-Intel] Clicked login button: '{btn['text']}'")
                            return True
                    except:
                        pass

        visible_btns = [b for b in snap.buttons if b.get("text") and len(b["text"]) > 2]
        if visible_btns:
            visible_btns.sort(key=lambda b: len(b["text"]), reverse=True)
            for btn in visible_btns[:3]:
                try:
                    el = self.page.get_by_text(btn["text"], exact=False).first
                    if el and el.is_visible():
                        el.click()
                        print(f"[DOM-Intel] Clicked prominent button: '{btn['text']}'")
                        return True
                except:
                    pass

        for link in snap.links:
            txt = link.get("text", "").lower()
            if intent == Intent.SIGNUP and self._is_signup_text(txt):
                try:
                    href = link.get("href", "")
                    if href and not href.startswith("javascript:"):
                        self.page.goto(href)
                        print(f"[DOM-Intel] Navigated to signup link: '{link['text']}'")
                        return True
                except:
                    pass
            if intent == Intent.SIGNIN and self._is_login_text(txt):
                try:
                    href = link.get("href", "")
                    if href and not href.startswith("javascript:"):
                        self.page.goto(href)
                        print(f"[DOM-Intel] Navigated to login link: '{link['text']}'")
                        return True
                except:
                    pass

        print("[DOM-Intel] Nothing actionable found on page")
        return False

    def _click_any_button(self) -> bool:
        print("[DOM-Intel] Clicking most prominent button...")
        snap = self.capture()

        priority_keywords = ["submit", "continue", "next", "save", "done", "finish", "confirm", "agree", "accept"]
        for kw in priority_keywords:
            for btn in snap.buttons:
                if kw in btn.get("text", "").lower():
                    try:
                        el = self.page.get_by_text(btn["text"], exact=False).first
                        if el and el.is_visible():
                            el.click()
                            print(f"[DOM-Intel] Clicked priority button: '{btn['text']}'")
                            return True
                    except:
                        pass

        visible_btns = [b for b in snap.buttons if b.get("text") and len(b["text"]) > 2]
        if visible_btns:
            visible_btns.sort(key=lambda b: len(b["text"]), reverse=True)
            for btn in visible_btns[:3]:
                try:
                    el = self.page.get_by_text(btn["text"], exact=False).first
                    if el and el.is_visible():
                        el.click()
                        print(f"[DOM-Intel] Clicked prominent button: '{btn['text']}'")
                        return True
                except:
                    pass

        btns = self.page.query_selector_all("button")
        for b in btns:
            try:
                if b.is_visible():
                    b.click()
                    print(f"[DOM-Intel] Clicked first visible button: '{b.inner_text().strip()[:50]}'")
                    return True
            except:
                pass

        return False

    def _click_skip_button(self) -> bool:
        skip_texts = ["skip", "later", "remind me later", "do this later", "not now", "continue", "next", "i'll do this later"]
        for text in skip_texts:
            try:
                el = self.page.get_by_text(text, exact=False).first
                if el and el.is_visible():
                    el.click()
                    print(f"[DOM-Intel] Clicked skip: '{text}'")
                    self.page.wait_for_timeout(1000)
                    return True
            except:
                pass
        for text in skip_texts[:4]:
            try:
                btn = self.page.get_by_role("button", name=re.compile(text, re.I)).first
                if btn and btn.is_visible():
                    btn.click()
                    print(f"[DOM-Intel] Clicked skip button: '{text}'")
                    return True
            except:
                pass
        return False

    def _delegate_to_human(self, state: PageState):
        instructions = self.HUMAN_INSTRUCTIONS.get(state, [])
        for line in instructions:
            print(line)
        return self.wait_for_dom_change(timeout_seconds=300, poll_interval=2.0)
