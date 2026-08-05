#!/usr/bin/env python3
"""
Make.com Webhook Handlers for ManyChat + Gumroad Integration
Deploy as webhook endpoints (use ngrok for local testing, or deploy to cloud)

Endpoints:
- POST /webhook/manychat/conversion - Track ManyChat blueprint requests
- POST /webhook/gumroad/ping - Gumroad ping (sale notifications)
- POST /webhook/make/daily-trigger - Trigger daily video generation
"""

import os
import json
import hmac
import hashlib
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Config
MAKE_WEBHOOK_SECRET = os.getenv("MAKE_WEBHOOK_SECRET", "your_secret_here")
GUMROAD_WEBHOOK_SECRET = os.getenv("GUMROAD_WEBHOOK_SECRET", "your_secret_here")
GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_CONTENT_PIPELINE_ID")
GOOGLE_SHEETS_TAB = os.getenv("GOOGLE_SHEETS_TAB_NAME", "Sheet1")

class WebhookHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
    
    def _verify_signature(self, payload, signature, secret):
        """Verify webhook signature"""
        expected = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected}", signature)
    
    def log_request(self, code='-', size='-'):
        pass  # Suppress default logging
    
    def do_GET(self):
        """Health check"""
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._set_headers()
            self.wfile.write(json.dumps({"status": "ok", "time": datetime.now().isoformat()}).encode())
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not found"}).encode())
    
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        payload = self.rfile.read(content_length)
        
        try:
            data = json.loads(payload.decode()) if payload else {}
        except json.JSONDecodeError:
            data = {}
        
        print(f"\n🔔 Webhook: {path}")
        print(f"   Data: {json.dumps(data, indent=2)[:500]}")
        
        if path == "/webhook/manychat/conversion":
            self.handle_manychat_conversion(data)
        elif path == "/webhook/gumroad/ping":
            self.handle_gumroad_ping(data, payload)
        elif path == "/webhook/make/daily-trigger":
            self.handle_make_trigger(data)
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Unknown endpoint"}).encode())
    
    def handle_manychat_conversion(self, data):
        """Track ManyChat blueprint request → log to Google Sheets"""
        # Expected data from ManyChat external request:
        # {
        #   "event": "blueprint_requested",
        #   "user_id": "12345",
        #   "username": "user123",
        #   "keyword": "MAGNETIC",
        #   "post_id": "instagram_post_id",
        #   "timestamp": "2026-01-15T10:30:00Z"
        # }
        
        event = data.get("event")
        if event != "blueprint_requested":
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Invalid event"}).encode())
            return
        
        # Log to Google Sheets (Analytics tab)
        # In production, use Google Sheets API
        log_entry = {
            "timestamp": data.get("timestamp", datetime.now().isoformat()),
            "user_id": data.get("user_id"),
            "username": data.get("username"),
            "keyword": data.get("keyword"),
            "post_id": data.get("post_id"),
            "source": "manychat"
        }
        
        # Append to local log file (fallback)
        log_file = Path(__file__).parent.parent / "logs" / "manychat_conversions.jsonl"
        log_file.parent.mkdir(exist_ok=True)
        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        print(f"   ✅ Logged conversion: {data.get('username')} via {data.get('keyword')}")
        
        self._set_headers()
        self.wfile.write(json.dumps({"status": "logged", "entry": log_entry}).encode())
    
    def handle_gumroad_ping(self, data, raw_payload=None):
        """Handle Gumroad sale notification"""
        signature = self.headers.get('X-Gumroad-Signature', '')
        if GUMROAD_WEBHOOK_SECRET != "your_secret_here":
            if not self._verify_signature(raw_payload or b"", signature, GUMROAD_WEBHOOK_SECRET):
                self._set_headers(401)
                self.wfile.write(json.dumps({"error": "Invalid signature"}).encode())
                return

        # Gumroad sends: sale_id, product_id, product_name, email, price, etc.
        sale_data = {
            "timestamp": datetime.now().isoformat(),
            "sale_id": data.get("sale_id"),
            "product_id": data.get("product_id"),
            "product_name": data.get("product_name"),
            "customer_email": data.get("email"),
            "price": data.get("price"),
            "currency": data.get("currency", "USD"),
            "source": "gumroad"
        }

        # Log sale
        log_file = Path(__file__).parent.parent / "logs" / "gumroad_sales.jsonl"
        log_file.parent.mkdir(exist_ok=True)
        with open(log_file, "a") as f:
            f.write(json.dumps(sale_data) + "\n")

        print(f"   💰 Sale: {data.get('product_name')} - ${data.get('price')}")

        # Trigger post-purchase sequence (could call Make.com webhook)
        self._trigger_post_purchase(sale_data)

        self._set_headers()
        self.wfile.write(json.dumps({"status": "processed"}).encode())
    
    def handle_make_trigger(self, data):
        """Trigger daily video generation from Make.com"""
        # Verify secret
        provided_secret = self.headers.get('X-Make-Secret', '')
        if provided_secret != MAKE_WEBHOOK_SECRET:
            self._set_headers(401)
            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())
            return
        
        # This would trigger the Make.com scenario
        # In practice, Make.com calls this webhook to confirm completion
        print(f"   🔄 Make.com trigger received")
        
        self._set_headers()
        self.wfile.write(json.dumps({"status": "triggered"}).encode())
    
    def _trigger_post_purchase(self, sale_data):
        """Trigger post-purchase automation (Make.com webhook)"""
        make_webhook = os.getenv("MAKE_POST_PURCHASE_WEBHOOK")
        if make_webhook:
            import requests
            try:
                requests.post(make_webhook, json=sale_data, timeout=5)
            except Exception as e:
                print(f"   ⚠️ Failed to trigger Make.com: {e}")


def run_server(port=8080):
    """Run webhook server"""
    server = HTTPServer(('', port), WebhookHandler)
    print(f"🚀 Webhook server running on port {port}")
    print(f"   Endpoints:")
    print(f"   POST http://localhost:{port}/webhook/manychat/conversion")
    print(f"   POST http://localhost:{port}/webhook/gumroad/ping")
    print(f"   POST http://localhost:{port}/webhook/make/daily-trigger")
    print(f"   GET  http://localhost:{port}/health")
    print(f"\n   For production: Use ngrok → https://xxx.ngrok.io/webhook/...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)