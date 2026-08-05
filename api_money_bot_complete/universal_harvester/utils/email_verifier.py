#!/usr/bin/env python3
"""
Gmail Email Verification Automation (FIXED v2)
===============================================
Uses IMAP to read verification emails and extract codes/links.
Requires Gmail App Password (not main password) with IMAP enabled.

FIXES APPLIED:
- Fixed IMAP OR chain parenthesization (RFC 3501 compliant)
- Added connection health checks (NOOP) and auto-reconnect
- Fixed subject decoding for multipart-encoded subjects
- Added reconnection logic in all polling loops
- Fixed Gmail alias IMAP search syntax (removed incorrect parens)
- Added TempMail API error handling
- Improved platform matching with domain aliases
- Added connection liveness validation before each search
- Fixed exception handling to attempt recovery instead of silent swallowing
"""

import os
import re
import imaplib
import email
import time
import requests
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timedelta
from email.header import decode_header


class IMAPVerifier:
    """Automated email verification code/link extractor (Gmail + ProtonMail)."""

    def __init__(self, email_addr: str = None, password: str = None, imap_server: str = None):
        self.email_addr = email_addr or os.getenv("GMAIL_EMAIL") or os.getenv("EMAIL_ADDR")
        self.password = password or os.getenv("GMAIL_APP_PASSWORD") or os.getenv("EMAIL_PASSWORD")

        if imap_server:
            self.imap_server = imap_server
        elif self.email_addr and "protonmail" in self.email_addr.lower():
            self.imap_server = "imap.protonmail.ch"
        else:
            self.imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")

        self.imap_port = int(os.getenv("IMAP_PORT", 993))
        self.connection = None
        self._last_activity = 0.0
        self._connection_timeout = 300

    def _is_connected(self) -> bool:
        """Check if IMAP connection is still alive using NOOP."""
        if not self.connection:
            return False
        try:
            status, _ = self.connection.noop()
            if status == "OK":
                self._last_activity = time.time()
                return True
            return False
        except (imaplib.IMAP4.abort, imaplib.IMAP4.error, OSError, BrokenPipeError):
            return False

    def connect(self) -> bool:
        """Establish IMAP connection with retry logic."""
        if not self.email_addr or not self.password:
            print("[IMAP] Email or password not set")
            return False

        if self.connection:
            try:
                self.connection.close()
                self.connection.logout()
            except Exception:
                pass
            self.connection = None

        try:
            self.connection = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            self.connection.login(self.email_addr, self.password)
            self.connection.select("INBOX")
            self._last_activity = time.time()
            print(f"[IMAP] Connected to {self.email_addr} via {self.imap_server}")
            return True
        except Exception as e:
            print(f"[IMAP] Connection failed: {e}")
            self.connection = None
            return False

    def disconnect(self):
        """Close IMAP connection cleanly."""
        if self.connection:
            try:
                self.connection.close()
                self.connection.logout()
            except Exception:
                pass
            self.connection = None

    def _ensure_connection(self) -> bool:
        """Ensure connection is alive, reconnect if needed."""
        if not self._is_connected():
            print("[IMAP] Connection lost or stale, reconnecting...")
            return self.connect()
        if time.time() - self._last_activity > self._connection_timeout:
            print("[IMAP] Connection idle too long, refreshing...")
            return self.connect()
        return True

    def _build_or_chain(self, keyword: str, values: List[str]) -> str:
        """
        Build proper IMAP prefix-OR chain per RFC 3501.
        IMAP SEARCH syntax requires OR to be prefix-binary: OR <criteria1> <criteria2>
        For multiple values, this nests: OR <val1> OR <val2> <val3>
        The entire chain must be parenthesized when combined with other criteria.
        """
        if not values:
            return ""
        if len(values) == 1:
            return f'{keyword} "{values[0]}"'
        result = f'{keyword} "{values[-1]}"'
        for val in reversed(values[:-1]):
            result = f'OR {keyword} "{val}" {result}'
        return f"({result})"

    def search_verification_email(
        self,
        sender_keywords: List[str] = None,
        subject_keywords: List[str] = None,
        since_minutes: int = 10,
        max_results: int = 5
    ) -> List[Dict]:
        """Search for verification emails with proper IMAP syntax."""
        if not self._ensure_connection():
            return []

        criteria_parts = []
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        dt = datetime.now() - timedelta(minutes=since_minutes)
        since_date = f"{dt.day:02d}-{months[dt.month - 1]}-{dt.year}"
        criteria_parts.append(f'SINCE "{since_date}"')

        if sender_keywords:
            sender_part = self._build_or_chain("FROM", sender_keywords)
            if sender_part:
                criteria_parts.append(sender_part)

        if subject_keywords:
            subject_part = self._build_or_chain("SUBJECT", subject_keywords)
            if subject_part:
                criteria_parts.append(subject_part)

        search_criteria = " ".join(criteria_parts)

        try:
            status, messages = self.connection.search(None, search_criteria)
            if status != "OK":
                print(f"[IMAPVerifier] Search failed with status: {status}")
                return []
            email_ids = messages[0].split()
            if not email_ids:
                return []
            email_ids = email_ids[-max_results:][::-1]
            results = []
            for eid in email_ids:
                email_data = self._fetch_email(eid)
                if email_data:
                    results.append(email_data)
            return results
        except Exception as e:
            print(f"[IMAPVerifier] Search error: {e}")
            self._last_activity = 0
            return []

    def _fetch_email(self, email_id: bytes) -> Optional[Dict]:
        """Fetch and parse a single email."""
        try:
            status, msg_data = self.connection.fetch(email_id, "(RFC822)")
            if status != "OK":
                return None
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            subject = self._decode_header_value(msg.get("Subject", ""))
            sender = msg.get("From", "")
            body = self._get_email_body(msg)
            return {
                "id": email_id.decode(),
                "subject": subject,
                "sender": sender,
                "body": body,
                "date": msg.get("Date", "")
            }
        except Exception as e:
            print(f"[IMAPVerifier] Fetch error: {e}")
            return None

    def _decode_header_value(self, value: str) -> str:
        """Properly decode email header value, handling multipart encoding."""
        if not value:
            return ""
        try:
            parts = decode_header(value)
            decoded_parts = []
            for part, charset in parts:
                if isinstance(part, bytes):
                    try:
                        decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
                    except (LookupError, UnicodeDecodeError):
                        decoded_parts.append(part.decode("utf-8", errors="replace"))
                else:
                    decoded_parts.append(part)
            return "".join(decoded_parts)
        except Exception as e:
            print(f"[IMAPVerifier] Header decode error: {e}")
            return str(value)

    def _get_email_body(self, msg) -> str:
        """Extract text body from email (handles multipart)."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(charset, errors="replace")
                            break
                    except Exception:
                        continue
                elif content_type == "text/html" and "attachment" not in content_disposition and not body:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(charset, errors="replace")
                    except Exception:
                        continue
        else:
            charset = msg.get_content_charset() or "utf-8"
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(charset, errors="replace")
            except Exception:
                pass
        return body

    def extract_verification_code(self, body: str, patterns: List[str] = None) -> Optional[str]:
        """Extract verification code from email body."""
        default_patterns = [
            r'(?:code|verification|otp|pin|token)[\s#:=]+(\d{6})',
            r'(?:code|verification|otp|pin|token)[\s#:=]+(\d{4,8})',
            r'\b(\d{6})\b',
            r'\b(\d{4,8})\b',
            r'(?:is|was)[\s:]+(\d{6})',
            r'(?:is|was)[\s:]+(\d{4,8})',
        ]
        search_patterns = patterns or default_patterns
        for pattern in search_patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            if matches:
                return max(matches, key=len)
        return None

    def extract_verification_link(self, body: str, domain_keywords: List[str] = None) -> Optional[str]:
        """Extract verification link from email body."""
        url_pattern = r'https?://[^\s<>"\']+'
        urls = re.findall(url_pattern, body)
        if domain_keywords:
            for url in urls:
                for kw in domain_keywords:
                    if kw.lower() in url.lower():
                        return url
        else:
            for url in urls:
                if any(kw in url.lower() for kw in ["verify", "confirm", "activate", "auth", "token", "code", "validation"]):
                    return url
        return urls[0] if urls else None

    def wait_for_verification(
        self,
        sender_keywords: List[str],
        subject_keywords: List[str] = None,
        timeout_seconds: int = 120,
        poll_interval: int = 10
    ) -> Optional[Dict]:
        """Wait for verification email and extract code/link with auto-reconnect."""
        print(f"[IMAPVerifier] Waiting for verification email (timeout: {timeout_seconds}s)...")
        start_time = time.time()
        subject_kw = subject_keywords or ["verify", "confirm", "code", "activate", "welcome", "verification"]
        consecutive_errors = 0
        max_consecutive_errors = 3

        while time.time() - start_time < timeout_seconds:
            if not self._ensure_connection():
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    print("[IMAPVerifier] Too many connection failures, aborting.")
                    return None
                time.sleep(min(poll_interval, 5))
                continue

            try:
                emails = self.search_verification_email(
                    sender_keywords=sender_keywords,
                    subject_keywords=subject_kw,
                    since_minutes=5,
                    max_results=3
                )
                consecutive_errors = 0
                for email_data in emails:
                    body = email_data["body"]
                    code = self.extract_verification_code(body)
                    link = self.extract_verification_link(body, sender_keywords)
                    if code or link:
                        print(f"[IMAPVerifier] Found verification - Code: {code}, Link: {link}")
                        return {"code": code, "link": link, "email": email_data}
            except Exception as e:
                consecutive_errors += 1
                print(f"[IMAPVerifier] Poll error ({consecutive_errors}/{max_consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    print("[IMAPVerifier] Too many errors, aborting.")
                    return None
                self._last_activity = 0

            elapsed = int(time.time() - start_time)
            print(f"[IMAPVerifier] Waiting... ({elapsed}s elapsed)")
            time.sleep(poll_interval)

        print("[IMAPVerifier] Timeout - no verification email found")
        return None


class TempMailVerifier:
    """Disposable email verifier using Mail.tm API — no account needed."""

    API_BASE = "https://api.mail.tm"
    SENDER_MAP = {
        "binance": ["binance.com", "mail.binance.com", "noreply@binance.com"],
        "coinbase": ["coinbase.com", "mail.coinbase.com", "no-reply@coinbase.com"],
        "bybit": ["bybit.com", "mail.bybit.com", "noreply@bybit.com"],
        "kucoin": ["kucoin.com", "mail.kucoin.com", "noreply@kucoin.com"],
        "okx": ["okx.com", "mail.okx.com", "noreply@okx.com"],
        "github": ["github.com", "noreply@github.com"],
        "upwork": ["upwork.com", "mail.upwork.com"],
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.email = None
        self.password = None
        self.token = None
        self.account_id = None

    def _api_get(self, endpoint: str, **kwargs) -> Optional[Dict]:
        """Safe API GET with error handling."""
        try:
            resp = self.session.get(f"{self.API_BASE}{endpoint}", timeout=10, **kwargs)
            if resp.status_code == 200:
                return resp.json()
            print(f"[TempMail] API GET {endpoint} failed: {resp.status_code}")
            return None
        except requests.RequestException as e:
            print(f"[TempMail] API GET {endpoint} error: {e}")
            return None
        except ValueError as e:
            print(f"[TempMail] API GET {endpoint} JSON decode error: {e}")
            return None

    def _api_post(self, endpoint: str, json_data: Dict = None, **kwargs) -> Tuple[Optional[Dict], int]:
        """Safe API POST with error handling. Returns (data, status_code)."""
        try:
            resp = self.session.post(
                f"{self.API_BASE}{endpoint}",
                json=json_data,
                timeout=10,
                **kwargs
            )
            try:
                data = resp.json() if resp.text else {}
            except ValueError:
                data = {"raw_response": resp.text}
            return data, resp.status_code
        except requests.RequestException as e:
            print(f"[TempMail] API POST {endpoint} error: {e}")
            return None, 0

    def create_inbox(self) -> str:
        """Create a disposable inbox. Returns email address."""
        import random
        import string

        domains_resp = self._api_get("/domains")
        if not domains_resp:
            raise Exception("Failed to fetch Mail.tm domains")

        domains_list = domains_resp.get("hydra:member", []) if isinstance(domains_resp, dict) else []
        if not domains_list:
            raise Exception("No mail.tm domains available")

        domain = domains_list[0]["domain"]
        rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        self.email = f"moneybot_{rand}@{domain}"
        self.password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))

        resp_data, status = self._api_post("/accounts", {
            "address": self.email,
            "password": self.password
        })
        if status not in (200, 201):
            raise Exception(f"Failed to create inbox: {status} {resp_data}")

        self.account_id = resp_data.get("id") if resp_data else None

        token_data, token_status = self._api_post("/token", {
            "address": self.email,
            "password": self.password
        })
        if token_status != 200 or not token_data:
            raise Exception(f"Failed to get auth token: {token_status}")

        self.token = token_data.get("token")
        if not self.token:
            raise Exception("No token in auth response")

        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        print(f"[TempMail] Created inbox: {self.email}")
        return self.email

    def check_messages(self) -> List[Dict]:
        """Fetch all messages in inbox with error handling."""
        if not self.token:
            return []

        msgs_data = self._api_get("/messages")
        if not msgs_data:
            return []

        msgs = msgs_data.get("hydra:member", []) if isinstance(msgs_data, dict) else []
        results = []

        for msg in msgs:
            msg_id = msg.get("id")
            if not msg_id:
                continue

            detail = self._api_get(f"/messages/{msg_id}")
            if not detail:
                continue

            html = detail.get("html", "") or []
            body = "\n".join(html) if isinstance(html, list) else str(html)

            from_addr = detail.get("from", {})
            results.append({
                "id": msg_id,
                "subject": detail.get("subject", ""),
                "sender": from_addr.get("address", "") if isinstance(from_addr, dict) else str(from_addr),
                "body": body,
                "date": detail.get("createdAt", ""),
            })

        return results

    def extract_verification_code(self, body: str) -> Optional[str]:
        """Extract verification code from email body."""
        patterns = [
            r"(?:code|verification|otp|pin|token)[\s#:=]+(\d{6})",
            r"\b(\d{6})\b",
            r"\b(\d{4,8})\b",
            r"(?:is|was)[\s:]+(\d{6})",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            if matches:
                for m in matches:
                    if len(str(m)) == 6:
                        return str(m)
                return str(matches[0])
        return None

    def wait_for_code(self, platform: str, timeout: int = 120) -> Optional[Dict]:
        """Poll for verification email and extract code with error recovery."""
        print(f"[TempMail] Waiting for {platform} verification email (timeout {timeout}s)...")

        sender_kw = self.SENDER_MAP.get(platform.lower(), [platform.lower()])
        deadline = time.time() + timeout
        consecutive_errors = 0
        max_errors = 5

        while time.time() < deadline:
            try:
                msgs = self.check_messages()
                consecutive_errors = 0

                for msg in msgs:
                    sender = msg.get("sender", "").lower()
                    if any(kw.lower() in sender for kw in sender_kw):
                        code = self.extract_verification_code(msg["body"])
                        if code:
                            print(f"[TempMail] Found code: {code}")
                            return {"code": code, "email_data": msg}

            except Exception as e:
                consecutive_errors += 1
                print(f"[TempMail] Poll error ({consecutive_errors}/{max_errors}): {e}")
                if consecutive_errors >= max_errors:
                    print("[TempMail] Too many errors, aborting.")
                    return None

            time.sleep(5)

        print("[TempMail] Timeout - no verification email")
        return None

    def cleanup(self):
        """Delete the disposable inbox."""
        if self.account_id:
            try:
                self.session.delete(f"{self.API_BASE}/accounts/{self.account_id}", timeout=10)
            except Exception:
                pass


class GmailAliasVerifier:
    """
    Verify emails sent to a Gmail plus-alias (user+tag@gmail.com) via IMAP.
    Uses GMAIL_EMAIL / GMAIL_APP_PASSWORD from .env for IMAP auth.
    """

    def __init__(self, alias_email: str):
        self.alias = alias_email
        self.base_email = os.getenv("GMAIL_EMAIL")
        self.app_password = os.getenv("GMAIL_APP_PASSWORD")
        self._connection = None
        self._last_activity = 0.0

    def _is_connected(self) -> bool:
        """Check if IMAP connection is alive."""
        if not self._connection:
            return False
        try:
            status, _ = self._connection.noop()
            return status == "OK"
        except Exception:
            return False

    def _connect(self) -> bool:
        if not self.base_email or not self.app_password:
            print("[GmailAlias] GMAIL_EMAIL or GMAIL_APP_PASSWORD not set")
            return False

        if self._connection:
            try:
                self._connection.close()
                self._connection.logout()
            except Exception:
                pass

        try:
            self._connection = imaplib.IMAP4_SSL("imap.gmail.com", 993)
            self._connection.login(self.base_email, self.app_password)
            self._connection.select("INBOX")
            self._last_activity = time.time()
            return True
        except Exception as e:
            print(f"[GmailAlias] IMAP connect failed: {e}")
            self._connection = None
            return False

    def _ensure_connection(self) -> bool:
        """Ensure connection is alive, reconnect if needed."""
        if not self._is_connected():
            return self._connect()
        if time.time() - self._last_activity > 300:
            return self._connect()
        return True

    def _disconnect(self):
        if self._connection:
            try:
                self._connection.close()
                self._connection.logout()
            except Exception:
                pass
            self._connection = None

    def extract_verification_code(self, body: str) -> Optional[str]:
        """Extract verification code from email body."""
        patterns = [
            r"(?:code|verification|otp|pin|token)[\s#:=]+(\d{6})",
            r"\b(\d{6})\b",
            r"\b(\d{4,8})\b",
            r"(?:is|was)[\s:]+(\d{6})",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, body, re.IGNORECASE)
            if matches:
                for m in matches:
                    if len(str(m)) == 6:
                        return str(m)
                return str(matches[0])
        return None

    def _matches_platform(self, sender: str, platform: str) -> bool:
        """Improved platform matching with aliases."""
        sender_lower = sender.lower()
        platform_lower = platform.lower()

        if platform_lower in sender_lower:
            return True

        aliases = {
            "twitter": ["twitter.com", "x.com"],
            "x": ["x.com", "twitter.com"],
        }

        for alias, domains in aliases.get(platform_lower, {}).items():
            if any(d in sender_lower for d in domains):
                return True

        return False

    def wait_for_code(self, platform: str, timeout: int = 180) -> Optional[Dict]:
        """Poll Gmail inbox for an email addressed to the alias."""
        print(f"[GmailAlias] Waiting for {platform} email to {self.alias}...")

        if not self._ensure_connection():
            return None

        search_criteria = f'TO "{self.alias}"'

        deadline = time.time() + timeout
        consecutive_errors = 0
        max_errors = 3

        while time.time() < deadline:
            if not self._ensure_connection():
                consecutive_errors += 1
                if consecutive_errors >= max_errors:
                    return None
                time.sleep(5)
                continue

            try:
                status, ids = self._connection.search(None, search_criteria)
                consecutive_errors = 0

                if status == "OK" and ids[0]:
                    for msg_id in ids[0].split():
                        status, data = self._connection.fetch(msg_id, "(RFC822)")
                        if status != "OK":
                            continue

                        raw = data[0][1] if isinstance(data[0], tuple) else data[0]
                        msg = email.message_from_bytes(raw)

                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        body = payload.decode(errors="replace")
                                    break
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                body = payload.decode(errors="replace")

                        sender = msg.get("From", "").lower()
                        if self._matches_platform(sender, platform):
                            code = self.extract_verification_code(body)

                            link = None
                            link_match = re.search(
                                r"https?://[^\s\"\']*(?:verify|confirm|activate)[^\s\"\']*",
                                body,
                                re.IGNORECASE
                            )
                            if link_match:
                                link = link_match.group(0)

                            result = {
                                "code": code,
                                "email_data": {
                                    "subject": msg.get("Subject", ""),
                                    "from": sender,
                                    "body": body[:2000]
                                }
                            }
                            if link:
                                result["link"] = link

                            if code or link:
                                found_parts = []
                                if code:
                                    found_parts.append(f"code: {code}")
                                if link:
                                    found_parts.append("link")
                                print(f"[GmailAlias] Found {' and '.join(found_parts)}")
                                return result

            except Exception as e:
                consecutive_errors += 1
                print(f"[GmailAlias] Poll error ({consecutive_errors}/{max_errors}): {e}")
                if consecutive_errors >= max_errors:
                    return None
                self._last_activity = 0

            time.sleep(5)

        print("[GmailAlias] Timeout — no email found")
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._disconnect()


def wait_for_email_verification(
    platform: str,
    email_addr: str = None,
    password: str = None,
    imap_server: str = None,
    timeout: int = 120
) -> Optional[Dict]:
    """
    Wait for verification email. Tries Gmail/IMAP first, then falls back to Mail.tm.
    """
    sender_map = {
        "binance": ["binance.com", "mail.binance.com", "noreply@binance.com"],
        "coinbase": ["coinbase.com", "mail.coinbase.com", "no-reply@coinbase.com"],
        "bybit": ["bybit.com", "mail.bybit.com", "noreply@bybit.com"],
        "kucoin": ["kucoin.com", "mail.kucoin.com", "noreply@kucoin.com"],
        "okx": ["okx.com", "mail.okx.com", "noreply@okx.com"],
        "github": ["github.com", "noreply@github.com"],
        "upwork": ["upwork.com", "mail.upwork.com"],
        "gumroad": ["gumroad.com", "mail.gumroad.com"],
        "stripe": ["stripe.com", "mail.stripe.com"],
        "openai": ["openai.com", "mail.openai.com"],
        "shutterstock": ["shutterstock.com", "mail.shutterstock.com"],
        "adobestock": ["adobe.com", "mail.adobe.com"],
        "pond5": ["pond5.com", "mail.pond5.com"],
        "etsy": ["etsy.com", "mail.etsy.com"],
        "ebay": ["ebay.com", "mail.ebay.com"],
        "shopify": ["shopify.com", "mail.shopify.com"],
        "printful": ["printful.com", "mail.printful.com"],
        "printify": ["printify.com", "mail.printify.com"],
        "medium": ["medium.com", "mail.medium.com"],
        "patreon": ["patreon.com", "mail.patreon.com"],
        "substack": ["substack.com", "mail.substack.com"],
        "reddit": ["reddit.com", "mail.reddit.com"],
        "twitter": ["twitter.com", "x.com", "mail.twitter.com"],
        "x": ["x.com", "twitter.com", "mail.twitter.com"],
        "anthropic": ["anthropic.com", "mail.anthropic.com"],
        "replicate": ["replicate.com", "mail.replicate.com"],
        "rapidapi": ["rapidapi.com", "mail.rapidapi.com"],
        "razorpay": ["razorpay.com", "mail.razorpay.com"],
        "wise": ["wise.com", "mail.wise.com", "transferwise.com"],
        "paypal": ["paypal.com", "mail.paypal.com"],
        "toloka": ["toloka.yandex.com", "yandex.com"],
        "clickworker": ["clickworker.com", "mail.clickworker.com"],
        "remotasks": ["remotasks.com", "mail.remotasks.com"],
    }

    sender_keywords = sender_map.get(platform.lower(), [platform.lower()])

    gmail = os.getenv("GMAIL_EMAIL", "")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")
    if gmail and gmail_pass and gmail != "your_email@gmail.com":
        verifier = IMAPVerifier(email_addr, password, imap_server)
        try:
            result = verifier.wait_for_verification(
                sender_keywords=sender_keywords, timeout_seconds=timeout
            )
            if result:
                return result
        finally:
            verifier.disconnect()

    print("[TempMail] IMAP not configured; using disposable inbox")
    tm = TempMailVerifier()
    try:
        return tm.wait_for_code(platform, timeout=timeout)
    finally:
        tm.cleanup()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = wait_for_email_verification(sys.argv[1])
        print(f"Result: {result}")
