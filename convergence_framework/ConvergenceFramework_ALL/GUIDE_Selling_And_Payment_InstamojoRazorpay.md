# Guide — Selling & Payment Setup (Instamojo / Razorpay), Step by Step

*For the seller/author. The complete flow: gate the file behind payment, collect in ₹ via UPI/cards, auto-deliver the kit, and settle to your Indian bank. Covers Instamojo (simplest for digital files) and Razorpay (best rates + control).*

By Kunal Das

> Not legal/tax advice. Confirm current fees, settlement cycles, and GST rules on each platform and with a CA before launch — they change.

---

## 0. The funnel (same on either platform)

**Free General prompt (email capture) → Paid full kit ₹499 → 1:1 session ₹2,999.**
LinkedIn drives attention; the platform gates payment and delivers the file. You never send the zip manually.

**Golden rule:** the LinkedIn CTA links to a **checkout page**, never the file. Payment clears → platform delivers.

---

## 1. Which platform?

| | **Instamojo** | **Razorpay** |
|---|---|---|
| Native digital file delivery | **Yes** (upload file → auto-sent after payment) | No native — use **Razorpay Webstore** (auto-deliver) or a webhook + Google Drive/Gmail (Pabbly/Zapier) |
| Fees (digital goods) | ~**5% + ₹3 + GST** | ~**2% + GST** |
| Settlement to bank | **T+3** (instant/same-day for +1% + GST) | **T+2** (instant options available) |
| Best for | Fastest way to sell a downloadable kit with zero integration | Lowest fees + control; you're OK doing a tiny bit of setup |
| UPI / cards | Yes | Yes |

**Recommendation:** Launch on **Instamojo** for speed (native delivery, no glue code). Once volume grows, move the checkout to **Razorpay Webstore** (or Razorpay + Pabbly) to save on fees. Many sellers run Instamojo for India + a Gumroad link for international.

---

## PART A — Instamojo (recommended for launch)

### A.1 Account + KYC
1. Sign up at instamojo.com. Complete **KYC** (PAN + bank account + a business/UPI detail). Payouts are blocked until KYC clears, so do this first.
2. Add your **bank account** for settlements.

### A.2 Create the paid product (the kit)
1. Dashboard → **Smart Page / Add Product** → type **Digital**.
2. **Upload** `ConvergenceFramework_Kit.zip` (the buyer kit — NOT the ALL zip with your marketing).
3. Title: `Feasibility-First Convergence Framework`. Price: **₹499** (launch). Add the description + a preview image.
4. Enable **automatic file delivery** (buyer gets the download link/email instantly after payment). Confirm UPI + cards are on.
5. Save → copy the **shareable payment link**. This is what you paste after "Comment KIT."

### A.3 Create the FREE lead magnet
1. Add a second product = the **General prompt** only, price **₹0**, require **email** to download. This builds your list.

### A.4 Create the 1:1 (₹2,999)
1. Add a product at **₹2,999** with a description of the 45-min session. In the post-purchase message/email, include your Cal.com/Calendly booking link so payment happens **before** booking.

### A.5 Delivery copy (paste into the product's confirmation email)
> Thanks for grabbing the Convergence Framework. Your download + license key are below. Start with QUICKSTART.md, then MASTER_GUIDE_Prompts.md. Reply to this email with what breaks — I read every one. — Kunal

### A.6 Test + go live
1. Do a real **₹1 test** (or use test mode) → confirm the download email arrives.
2. Check **payout settings** (default T+3; enable faster payout if you want). Go live.

---

## PART B — Razorpay (lower fees / more control)

Razorpay doesn't email files natively. Pick ONE of these delivery methods:

### Option 1 — Razorpay Webstore (no code, auto-deliver)
1. Sign up + KYC at razorpay.com. Activate the account.
2. Open **Razorpay Webstore** → **Add Product** → upload `ConvergenceFramework_Kit.zip`, set **₹499**, enable **automatic file delivery**.
3. Add the free General-prompt product (₹0) and the ₹2,999 session.
4. Publish → copy the store/product link. Done — this is the closest Razorpay equivalent to Instamojo.

### Option 2 — Payment Page/Button + webhook delivery (most control)
1. Create a **Payment Page** (Dashboard → Payment Pages) or **Payment Button**, price ₹499, branded, UPI + cards on. Share the URL.
2. Host the zip on **Google Drive** (restricted link) or a signed URL.
3. Automate delivery: set a **webhook** on the `payment.captured` event (Dashboard → Settings → Webhooks) pointing to a **Pabbly Connect / Zapier** workflow that emails the buyer the download link on success. (Search "Razorpay + Pabbly digital product delivery" for the exact recipe.)
4. Test a live ₹1 payment → confirm the automated email fires.

### B.3 Payout
- Add your bank; default settlement is **T+2** (instant/same-day options available for a fee). Verify current cycle in the dashboard.

---

## 2. Product copy (works on either platform)

- **Title:** `Feasibility-First Convergence Framework — Make Any LLM Finish Real Software`
- **Tagline:** `The difference was never the model — it's the method.`
- **Short desc:** Two battle-tested system prompts + guides that make ChatGPT/Claude/Gemini give a feasibility verdict first, converge without burning credits, and finish whole apps — runnable on free agents. Includes a bonus ATS resume/job-search pack.
- **License line (also inside the kit):** Personal, single-user license. Please don't redistribute — the free General prompt is the shareable one.

---

## 3. GST & compliance (India) — read this

- Selling through a payment gateway (Razorpay/Instamojo/Stripe) can trigger **mandatory GST registration** under Section 24(ix) of the CGST Act **even below the ₹20L threshold**, because you're treated as an e-commerce seller. Digital products are generally taxed at **18% GST**.
- Practical implication: either register for GST and price inclusive of it, or confirm your exact obligation with a CA before you launch. Factor platform fees (~2–5%) + GST into the ₹499 so your net is what you expect.
- Publish the pages platforms/PCI rules require: **Refund/Returns policy, Terms, Contact info, Privacy** — KYC/activation often needs these live.

---

## 4. Anti-piracy (mitigate, don't obsess)

- Turn on **license keys** where available.
- **Watermark the PDF** with the buyer's email/order ID on delivery.
- Keep the price low (₹499) so copying isn't worth the effort. Ship only the buyer kit; keep marketing files out.

---

## 5. Pre-launch checklist

- [ ] KYC approved, bank added
- [ ] Buyer kit (`ConvergenceFramework_Kit.zip`) uploaded, price ₹499, auto-delivery ON
- [ ] Free General-prompt product live (email capture)
- [ ] ₹2,999 session product live + booking link in confirmation
- [ ] Delivery email copy set; license line included
- [ ] Real test purchase → download + email confirmed
- [ ] Refund/Terms/Contact/Privacy pages published
- [ ] Payout cycle confirmed; faster-payout decided
- [ ] Checkout link ready to paste under the LinkedIn "Comment KIT" CTA
