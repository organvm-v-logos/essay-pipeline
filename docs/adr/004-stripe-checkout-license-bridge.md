# ADR 004: Stripe Checkout License Bridge

## Status

Accepted

## Date

2026-06-20

## Context

ADR 003 established the premium template gate: free templates remain readable,
and premium templates require a signed license key. The missing production
piece was the payment path. A buyer should be able to pay through a mainstream
checkout provider, and a successful paid event should produce the license key
that the existing CLI gate already understands.

We considered Stripe and Lemon Squeezy. Lemon Squeezy has productized digital
goods and licenses, but Stripe Checkout is a widely available baseline and is
already sufficient for this repository's needs: hosted checkout, one-time or
subscription prices, signed webhooks, and no hosted account system inside
essay-pipeline.

## Decision

Add `src/billing.py` as a Stripe bridge.

- `essay-billing checkout` creates a Stripe Checkout session for a known SKU
  using `STRIPE_SECRET_KEY` and `STRIPE_PRICE_<SKU>`.
- `essay-billing stripe-webhook` verifies the raw payload with
  `STRIPE_WEBHOOK_SECRET` and Stripe's `Stripe-Signature` header.
- Paid `checkout.session.completed` events issue perpetual one-time license
  keys for `premium-single` / `premium-bundle`.
- Active `customer.subscription.created`, `customer.subscription.updated`, and
  `customer.subscription.resumed` events issue expiring subscription license
  keys through the Stripe `current_period_end`.
- The premium feature gate remains in `src/template_store.py`; billing only
  creates the key consumed by that gate.

## Consequences

- Free-tier behavior is unchanged: `field-note` is readable without checkout or
  a key.
- The package does not need the Stripe SDK; the existing `httpx` dependency is
  enough for Checkout session creation, and webhook verification uses the
  standard library.
- Subscription access is still offline after a key is issued. Renewal requires
  processing the next active subscription webhook and delivering the new
  expiring key to the buyer.
- The HMAC trade-off from ADR 003 still applies: this is a deterrent-grade
  commercial gate for an open-source package, not DRM.
