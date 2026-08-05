"""
Webhook server — FastAPI app for Twilio voice webhooks and Cal.com event callbacks.
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from routes.twilio import handle_incoming_call, handle_status_callback
from routes.calcom import handle_booking_created, handle_booking_cancelled

logger = logging.getLogger("webhook_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Webhook server starting up")
    yield
    logger.info("Webhook server shutting down")


app = FastAPI(title="Voice Agent Clinic Webhook Server", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhooks/twilio/voice")
async def twilio_voice(request: Request):
    """Incoming call webhook from Twilio."""
    form = await request.form()
    # Convert MultiDict to plain dict
    form_dict = {key: value for key, value in form.items()}
    result = await handle_incoming_call(form_dict)
    return PlainTextResponse(result, media_type="text/xml")


@app.post("/webhooks/twilio/status")
async def twilio_status(request: Request):
    """Call status callback from Twilio."""
    form = await request.form()
    await handle_status_callback(dict(form))
    return PlainTextResponse("OK")


@app.post("/webhooks/calcom/booking")
async def calcom_booking(request: Request):
    """Cal.com booking event webhook."""
    payload = await request.json()
    event_type = payload.get("triggerEvent")
    if event_type == "BOOKING_CREATED":
        await handle_booking_created(payload)
    elif event_type == "BOOKING_CANCELLED":
        await handle_booking_cancelled(payload)
    else:
        logger.info(f"Unhandled Cal.com event: {event_type}")
    return JSONResponse({"received": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
