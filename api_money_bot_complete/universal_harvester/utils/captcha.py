#!/usr/bin/env python3
"""
Captcha Solver — 2Captcha Integration
=======================================
Supports reCAPTCHA v2/v3, hCaptcha, slider CAPTCHA (Binance), and image captcha.
"""

import requests
import time
import os


class CaptchaSolver:
    """2Captcha API wrapper."""

    BASE = "http://2captcha.com"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("CAPTCHA_API_KEY")

    def _check_api_key(self) -> bool:
        """Check if API key is configured."""
        if not self.api_key:
            print("[CaptchaSolver] CAPTCHA_API_KEY not configured")
            return False
        return True

    def _submit(self, payload: dict) -> str:
        """Submit captcha and return task ID."""
        if not self._check_api_key():
            raise ValueError("CAPTCHA_API_KEY missing — set in .env or pass to constructor")
        resp = requests.post(f"{self.BASE}/in.php", data=payload, timeout=30)
        if resp.status_code != 200:
            raise Exception(f"Failed to submit captcha: {resp.status_code}")
        if not resp.text.startswith("OK|"):
            raise Exception(f"2Captcha error: {resp.text}")
        return resp.text.split("|")[1]


    def _poll_result(self, task_id: str, timeout: int = 180) -> str:
        """Poll for captcha result."""
        for _ in range(timeout // 3):
            time.sleep(3)
            resp = requests.get(
                f"{self.BASE}/res.php",
                params={"key": self.api_key, "action": "get", "id": task_id},
                timeout=30
            )
            if resp.text.startswith("OK|"):
                return resp.text.split("|")[1]
            if "CAPCHA_NOT_READY" not in resp.text:
                raise Exception(f"2Captcha error: {resp.text}")
        raise TimeoutError("Captcha solving timed out")

    def solve_recaptcha(self, site_key: str, page_url: str, invisible: bool = False) -> str:
        """Solve Google reCAPTCHA v2/v3."""
        payload = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "invisible": 1 if invisible else 0,
            "json": 1,
        }
        task_id = self._submit(payload)
        return self._poll_result(task_id)

    def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "verify", min_score: float = 0.3) -> str:
        """Solve Google reCAPTCHA v3."""
        payload = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "version": "v3",
            "action": action,
            "min_score": min_score,
            "json": 1,
        }
        task_id = self._submit(payload)
        return self._poll_result(task_id)

    def solve_hcaptcha(self, site_key: str, page_url: str) -> str:
        """Solve hCaptcha."""
        payload = {
            "key": self.api_key,
            "method": "hcaptcha",
            "sitekey": site_key,
            "pageurl": page_url,
            "json": 1,
        }
        task_id = self._submit(payload)
        return self._poll_result(task_id)

    def solve_slider_captcha(self, image_b64: str, page_url: str = "") -> dict:
        """
        Solve slider/puzzle CAPTCHA (Binance style).
        Requires base64 encoded image of the CAPTCHA puzzle.
        Returns dict with 'x_offset' or 'angle' depending on CAPTCHA type.
        """
        payload = {
            "key": self.api_key,
            "method": "rotatecaptcha",  # For Binance-style slider/rotation
            "body": image_b64,
            "json": 1,
        }
        task_id = self._submit(payload)
        result = self._poll_result(task_id)
        # Result format: "OK|angle:x_offset" or just angle
        if "|" in result:
            parts = result.split("|")
            if len(parts) > 1:
                return {"angle": parts[0], "x_offset": parts[1]}
        return {"angle": result}

    def solve_slider_captcha_click(self, image_b64: str, page_url: str = "") -> dict:
        """
        Solve slider CAPTCHA that requires clicking specific points.
        Returns coordinates to click.
        """
        payload = {
            "key": self.api_key,
            "method": "coordinates",  # For click-based CAPTCHA
            "body": image_b64,
            "json": 1,
        }
        task_id = self._submit(payload)
        result = self._poll_result(task_id)
        # Result: "OK|x1,y1;x2,y2;..."
        if "|" in result:
            coords_str = result.split("|")[1]
            coords = []
            for pair in coords_str.split(";"):
                if "," in pair:
                    x, y = pair.split(",")
                    coords.append({"x": int(x), "y": int(y)})
            return {"coordinates": coords}
        return {"coordinates": []}

    def solve_image(self, image_path: str) -> str:
        """Solve image-based captcha."""
        with open(image_path, "rb") as f:
            resp = requests.post(
                f"{self.BASE}/in.php",
                data={"key": self.api_key, "method": "post"},
                files={"file": f},
                timeout=30
            )
        if not resp.text.startswith("OK|"):
            raise Exception(f"Image captcha error: {resp.text}")
        task_id = resp.text.split("|")[1]
        return self._poll_result(task_id)

    def inject_recaptcha_token(self, page, token: str):
        """Inject solved reCAPTCHA token into the page."""
        page.evaluate(f"""
            (function() {{
                var t = '{token}';
                var tas = document.querySelectorAll('#g-recaptcha-response, [name="g-recaptcha-response"]');
                tas.forEach(function(el) {{
                    el.innerHTML = t;
                    el.value = t;
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }});
                try {{
                    if (typeof ___grecaptcha_cfg !== 'undefined') {{
                        var clients = ___grecaptcha_cfg.clients;
                        if (clients) {{
                            Object.keys(clients).forEach(function(id) {{
                                var c = clients[id];
                                if (!c) return;
                                Object.keys(c).forEach(function(k) {{
                                    var v = c[k];
                                    if (typeof v === 'function') {{ try {{ v(t); }} catch(e) {{}} }}
                                    else if (v && typeof v.callback === 'function') {{ try {{ v.callback(t); }} catch(e) {{}} }}
                                }});
                                if (typeof c.callback === 'function') {{ try {{ c.callback(t); }} catch(e) {{}} }}
                            }});
                        }}
                    }}
                }} catch(e) {{}}
                try {{
                    if (typeof grecaptcha !== 'undefined') {{
                        grecaptcha.ready(function() {{
                            try {{ grecaptcha.execute(); }} catch(e) {{}}
                            try {{
                                var ids = grecaptcha.getWidgetIds ? grecaptcha.getWidgetIds() : [];
                                ids.forEach(function(id) {{ grecaptcha.execute(id); }});
                            }} catch(e) {{}}
                        }});
                    }}
                }} catch(e) {{}}
            }})();
        """)

    def inject_hcaptcha_token(self, page, token: str):
        """Inject solved hCaptcha token into the page."""
        page.evaluate(f"""
            const elem = document.querySelector('[name="h-captcha-response"]');
            if (elem) elem.value = '{token}';
            if (window.hcaptcha) {{
                try {{ window.hcaptcha.setResponse('{token}'); }} catch(e) {{}}
            }}
        """)
