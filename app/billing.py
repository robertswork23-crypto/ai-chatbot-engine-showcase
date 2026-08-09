"""Stripe subscription billing for Nivor Chat Pro — real Checkout, real
webhook signature verification, real billing-portal handoff. Gated on
STRIPE_SECRET_KEY the same way ai.py gates on OPENAI_API_KEY: degrades to a
clear error instead of crashing when unconfigured.
"""
import logging
import os

import stripe
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .config import config
from .db import User

logger = logging.getLogger(__name__)


def _stripe_ready() -> bool:
    key = os.getenv("STRIPE_SECRET_KEY")
    if key:
        stripe.api_key = key
    return bool(key)


def create_checkout_session(user: User) -> str:
    if not _stripe_ready() or not config.stripe_price_id:
        raise HTTPException(status_code=501, detail="Billing isn't configured on this deployment yet.")

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        customer_email=user.email,
        client_reference_id=str(user.id),
        line_items=[{"price": config.stripe_price_id, "quantity": 1}],
        success_url=f"{config.frontend_url}/?billing=success",
        cancel_url=f"{config.frontend_url}/?billing=cancel",
    )
    return session.url


def create_portal_session(user: User) -> str:
    if not _stripe_ready() or not user.stripe_customer_id:
        raise HTTPException(status_code=501, detail="No billing account on file yet.")

    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=config.frontend_url,
    )
    return session.url


async def handle_webhook(request: Request, db: Session) -> dict:
    if not _stripe_ready() or not config.stripe_webhook_secret:
        raise HTTPException(status_code=501, detail="Webhook isn't configured on this deployment yet.")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, config.stripe_webhook_secret)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id")
        if user_id:
            user = db.query(User).filter(User.id == int(user_id)).first()
            if user:
                user.plan = "pro"
                user.stripe_customer_id = data.get("customer")
                user.stripe_subscription_id = data.get("subscription")
                db.commit()
                logger.info(f"User {user.id} upgraded to pro via checkout")

    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        subscription_id = data.get("id")
        sub_status = data.get("status")
        user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
        if user:
            if event_type == "customer.subscription.deleted" or sub_status in (
                "canceled", "unpaid", "incomplete_expired",
            ):
                user.plan = "free"
            elif sub_status == "active":
                user.plan = "pro"
            db.commit()
            logger.info(f"User {user.id} plan synced to {user.plan} via subscription {sub_status}")

    return {"received": True}
