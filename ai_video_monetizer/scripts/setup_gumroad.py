#!/usr/bin/env python3
"""
Gumroad Product Setup Script
Creates products via API and configures order bump + email sequence.
Requires GUMROAD_ACCESS_TOKEN in .env
"""

import os
import sys
import json
import requests
from pathlib import Path

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "python-dotenv", "-q"], check=True)
    from dotenv import load_dotenv
    load_dotenv()

ACCESS_TOKEN = os.getenv("GUMROAD_ACCESS_TOKEN")
BASE_URL = "https://api.gumroad.com/v2"

if not ACCESS_TOKEN or ACCESS_TOKEN == "your_g...":
    print("❌ GUMROAD_ACCESS_TOKEN not set in .env")
    print("   Get it from: https://app.gumroad.com/api")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/x-www-form-urlencoded"
}

# Product definitions from blueprint
PRODUCTS = [
    {
        "name": "The Magnetism Blueprint: Subconscious Laws of Attraction",
        "description": """STOP CHASING. START ATTRACTING. 🖤

Have you ever wondered why some people effortlessly command a room, leaving an unforgettable impression without saying a single word? It isn't luck—it's subconscious psychology.

The Magnetism Blueprint is a strategic guide written for those who want to understand the silent currents of human connection.

What you'll unlock inside:
• The exact body language triggers that spark immediate psychological attraction
• How to utilize high-value mystery so you are consistently remembered
• The science of tension and how to navigate it confidently

Get instant access today for just $9.99. (Regularly $24.99).

Click "I want this!" to download your copy immediately.""",
        "price": 9.99,
        "currency": "usd",
        "custom_permalink": "magnetism-blueprint",
        "is_digital": True,
        "file_path": "../content/ebook_manuscript.md",  # Will upload this
        "product_type": "ebook"
    },
    {
        "name": "The Texting Framework Upgrade: 50 High-Tension Scripts",
        "description": """50 Copy-and-Paste High-Tension Texting Scripts across 5 phases:
• Phase 1: Opening Hooks (1-10) - Break pattern, create curiosity
• Phase 2: Push-Pull Effect (11-20) - Emotional rollercoaster
• Phase 3: Mystery Frame (21-30) - Become the puzzle they can't solve
• Phase 4: Deepening Tension (31-40) - High stakes vulnerability
• Phase 5: Close/Meetup Bridge (41-50) - Convert tension to dates

Plus advanced tactics: Triangle Glance sequence, Cliffhanger exits, Callback re-opens, Disqualification pivots, and customization templates.""",
        "price": 10.00,
        "currency": "usd",
        "custom_permalink": "texting-framework",
        "is_digital": True,
        "file_path": "../content/texting_framework.md",
        "product_type": "ebook"
    },
    {
        "name": "Attraction Masterclass: The Unshakable Frame System",
        "description": """The complete video masterclass for mastering magnetic presence.

Modules:
1. Frame Control Fundamentals - Outcome independence & abundance mindset
2. Silent Signals Mastery - Two-second rule, Triangle Glance, controlled motion
3. Subconscious Mirroring - Chameleon effect, vocal pacing, emotional echoing
4. The Power of Absence - Scarcity, Peak-End Rule, digital blackout
5. Textual Chemistry - Equilibrium, push-pull, breaking instant replies
6. Advanced Texting Workshop - Live breakdowns of real conversations
7. Unshakable Frame Under Pressure - Handling pullback, testing, rejection
8. Integration & Lifestyle - Building a magnetic life, not just tactics

Includes: Workbook, cheat sheets, private community access, lifetime updates.""",
        "price": 97.00,
        "currency": "usd",
        "custom_permalink": "attraction-masterclass",
        "is_digital": False,  # Could be video course
        "product_type": "course"
    }
]


def api_call(method, endpoint, data=None):
    """Make Gumroad API call"""
    try:
        url = f"{BASE_URL}{endpoint}"
        if method == "GET":
            resp = requests.get(url, headers={"Authorization": f"Bearer {ACCESS_TOKEN}"}, params=data)
        else:
            resp = requests.post(url, headers=HEADERS, data=data)

        if resp.status_code not in (200, 201):
            print(f"❌ API Error ({resp.status_code}): {resp.text}")
            return None
        return resp.json()
    except Exception as e:
        print(f"   ❌ {method} {endpoint} failed: {e}")
        return None


def create_product(product):
    """Create a product on Gumroad"""
    print(f"\n📦 Creating: {product['name']}")
    
    # Prepare data
    data = {
        "name": product["name"],
        "description": product["description"],
        "price": str(int(product["price"] * 100)),  # Gumroad uses cents
        "currency": product["currency"],
        "custom_permalink": product["custom_permalink"],
        "is_digital": "true" if product["is_digital"] else "false",
        "return_policy": "no_return"  # Digital products
    }
    
    result = api_call("POST", "/products", data)
    if not result:
        return None
    
    product_id = result["product"]["id"]
    print(f"   ✅ Created! Product ID: {product_id}")
    print(f"   🔗 URL: https://gumroad.com/l/{product['custom_permalink']}")
    
    # Upload file if digital
    if product["is_digital"] and product.get("file_path"):
        file_path = Path(__file__).parent.parent / product["file_path"]
        if file_path.exists():
            print(f"   📤 Uploading file: {file_path.name}")
            upload_file(product_id, file_path)
        else:
            print(f"   ⚠️ File not found: {file_path}")
    
    return product_id


def upload_file(product_id, file_path):
    """Upload product file"""
    url = f"{BASE_URL}/products/{product_id}/files"
    files = {"file": open(file_path, "rb")}
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    
    resp = requests.post(url, headers=headers, files=files)
    if resp.status_code in (200, 201):
        print(f"   ✅ File uploaded!")
    else:
        print(f"   ❌ Upload failed: {resp.text}")


def create_order_bump(main_product_id, bump_product_id):
    """Configure order bump: when buying main, offer bump at checkout"""
    print(f"\n🔗 Setting up Order Bump: {main_product_id} → {bump_product_id}")
    
    data = {
        "product_id": main_product_id,
        "upsell_product_id": bump_product_id,
        "upsell_type": "order_bump",
        "discount_price": "1000"  # $10.00 in cents
    }
    
    result = api_call("POST", f"/products/{main_product_id}/upsells", data)
    if result:
        print(f"   ✅ Order bump configured!")
    return result


def setup_email_sequence(product_id):
    """Configure post-purchase email workflow"""
    print(f"\n📧 Setting up email sequence for product: {product_id}")
    
    # Note: Gumroad's email workflow API is limited
    # This documents what to set up manually in dashboard
    sequence = [
        {
            "delay_hours": 0,
            "subject": "Your Magnetism Blueprint is here! 🖤",
            "purpose": "Instant delivery confirmation"
        },
        {
            "delay_hours": 24,
            "subject": "The #1 mistake killing your attraction...",
            "purpose": "Free value + soft pitch for Texting Framework"
        },
        {
            "delay_hours": 48,
            "subject": "50 scripts. One framework. 🪐",
            "purpose": "Hard pitch for $97 Masterclass"
        },
        {
            "delay_hours": 72,
            "subject": "Last chance: Masterclass at founder price",
            "purpose": "Urgency close for Masterclass"
        }
    ]
    
    print("   Configure in Gumroad Dashboard: Email → Workflows → New Workflow")
    for i, email in enumerate(sequence):
        print(f"   Email {i+1}: {email['delay_hours']}h delay - {email['subject']}")
        print(f"              Purpose: {email['purpose']}")
    
    return sequence


def main():
    print("=" * 60)
    print("GUMROAD PRODUCT SETUP - AI Video Monetizer")
    print("=" * 60)
    
    # Verify auth
    user = api_call("GET", "/user")
    if not user:
        print("❌ Failed to authenticate. Check GUMROAD_ACCESS_TOKEN")
        sys.exit(1)
    print(f"✅ Authenticated as: {user['user']['name']} ({user['user']['email']})")
    
    # Create products
    created_products = {}
    for product in PRODUCTS:
        pid = create_product(product)
        if pid:
            created_products[product["product_type"]] = {
                "id": pid,
                "name": product["name"],
                "permalink": product["custom_permalink"],
                "url": f"https://gumroad.com/l/{product['custom_permalink']}"
            }
    
    # Set up order bump (Blueprint → Texting Framework)
    if "ebook" in created_products and len(created_products) >= 2:
        # Find main and bump
        main = None
        bump = None
        for k, v in created_products.items():
            if "Blueprint" in v["name"]:
                main = v
            elif "Texting Framework" in v["name"]:
                bump = v
        
        if main and bump:
            create_order_bump(main["id"], bump["id"])
            print(f"\n🔗 Order Bump Active!")
            print(f"   Main: {main['url']}")
            print(f"   Bump: {bump['url']} (shown at checkout for +$10)")
    
    # Email sequence
    for k, v in created_products.items():
        if k == "ebook" and "Blueprint" in v["name"]:
            setup_email_sequence(v["id"])
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ SETUP COMPLETE")
    print("=" * 60)
    print("\n📋 Product URLs for ManyChat:")
    for k, v in created_products.items():
        print(f"   {v['name']}: {v['url']}")
    
    print("\n🔗 Add to ManyChat DM Button:")
    print(f"   {created_products.get('ebook', {}).get('url', 'N/A')}")
    
    print("\n📝 Next Steps:")
    print("   1. Go to Gumroad Dashboard → Products")
    print("   2. Edit each product → Upload cover images (dark luxury aesthetic)")
    print("   3. Set CTA button text: 'I want this!' / 'Get the Blueprint 🪐'")
    print("   4. Configure Email → Workflows (use sequence above)")
    print("   5. Copy Blueprint URL to ManyChat flow")


if __name__ == "__main__":
    main()