# Essay Template Library

The essay-pipeline ships a catalog of **schema-enforced essay templates** — the
same structural contracts the pipeline validates against, packaged as ready-to-
fill scaffolds. Copy a template, replace the `{{TOKENS}}`, and it passes
`essay-validate` against the editorial-standards frontmatter schema on the first
try.

One **free sample** is included. The rest are **premium**, unlocked with a
signed license key. One-time purchase keys are perpetual; subscription keys can
carry an expiration date. No activation server is required for reads.

## Catalog

| Template | Tier | Price | Best for |
| -------- | ---- | ----- | -------- |
| **Field Note** (`field-note`) | Free | — | Short, single-claim observations |
| **Building-in-Public Case Study** (`case-study`) | Premium | $49 single / bundle | Documenting a piece of work end to end |
| **Technical Deep Dive** (`technical-deep-dive`) | Premium | $49 single / bundle | Explaining how a component actually works |
| **Sprint Retrospective** (`sprint-retrospective`) | Premium | $49 single / bundle | Closing a sprint with plan-vs-reality honesty |
| **Release Announcement** (`announcement`) | Premium | $49 single / bundle | Shipping something and saying why it matters |
| **Argument Essay** (`argument-essay`) | Premium | $49 single / bundle | Taking a defensible position |

The canonical machine-readable catalog is [`templates/manifest.yaml`](../../templates/manifest.yaml).

## Pricing

| SKU | What you get | Price |
| --- | ------------ | ----- |
| `premium-single` | One named premium template | **$49** |
| `premium-bundle` | All premium templates + every future addition | **$99** |
| `premium-subscription` | Premium access through the active billing period | configured in Stripe |

One-time purchase. Each sale issues a license key tied to the buyer's email.
Subscription checkout is also supported with the `premium-subscription` SKU when
you configure a recurring Stripe Price.

## How it works

```
buy ──▶ Stripe Checkout ──▶ signed webhook ──▶ `essay-billing stripe-webhook`
                                                            │
                                      license key tied to buyer email
                                                            │
                          `essay-template list --license KEY`  (premium shows "unlocked")
                          `essay-template eject case-study --output my-essay.md --license KEY`
```

### 1. Browse (no key needed)

```bash
essay-template list
```

Free templates show `open`; premium templates show `locked`. A matching
`premium-single` key unlocks one premium row; a `premium-bundle` key unlocks
every premium row.

### 2. Read or copy a template

```bash
# Free — works with no key:
essay-template show field-note

# Premium — requires a matching single-template key or a bundle key:
essay-template eject case-study --output drafts/my-case-study.md --license EPK1.XXXX.YYYY
```

Without a valid key, premium templates exit with `LOCKED` and a pointer back to
this catalog.

### 3. Fill and validate

Replace every `{{TOKEN}}`, then validate before publishing:

```bash
essay-validate --posts-dir drafts/ \
  --schema ../editorial-standards/schemas/frontmatter-schema.yaml
```

## Licensing model (HMAC key check)

License keys are signed with **HMAC-SHA256** over a readable payload
(`sku | email | issued | optional expires`). Verification is fully offline —
the same shared secret signs and verifies. See [`src/license.py`](../../src/license.py) and the architecture note in
[`docs/adr/003-template-library-licensing.md`](../adr/003-template-library-licensing.md).

**For sellers.** Set a private signing secret. Stripe Checkout is the normal
sale path:

```bash
export ESSAY_PIPELINE_LICENSE_SECRET="your-long-random-private-secret"
export STRIPE_SECRET_KEY="sk_live_..."
export STRIPE_WEBHOOK_SECRET="whsec_..."
export STRIPE_PRICE_PREMIUM_BUNDLE="price_..."

essay-billing checkout \
  --sku premium-bundle \
  --success-url https://example.com/thanks \
  --cancel-url https://example.com/templates

# In your webhook handler/job, pass the raw JSON body plus Stripe-Signature:
essay-billing stripe-webhook --signature "$STRIPE_SIGNATURE" < stripe-event.json
# → LICENSE_ISSUED ... key: EPK1....
```

Manual issuance remains available for back-office or migration cases:

```bash
essay-license issue --email buyer@example.com --sku premium-bundle
# → EPK1.GEZDGNBV.MFRGGZDF...   (give this to the buyer)

essay-license issue --email buyer@example.com --sku premium-single --template case-study
# → EPK1.GEZDGNBV.MFRGGZDF...   (unlocks only case-study)
```

For subscriptions, configure a recurring Stripe Price and use:

```bash
export STRIPE_PRICE_PREMIUM_SUBSCRIPTION="price_..."
essay-billing checkout \
  --sku premium-subscription \
  --mode subscription \
  --email buyer@example.com \
  --success-url https://example.com/thanks \
  --cancel-url https://example.com/templates
```

Active `customer.subscription.created` / `updated` / `resumed` webhooks issue
an expiring license key through the current Stripe billing period.

**For buyers.** Verify a key you received:

```bash
essay-license verify --key EPK1.GEZDGNBV.MFRGGZDF...
```

> **Security note.** This is a deterrent-grade gate, not DRM: anyone holding the
> secret can mint keys, and an offline check can be bypassed by editing the
> source. That is an accepted trade-off for a no-server, one-time-purchase
> product. Protect the secret; rotate it (and re-issue keys) if it leaks. A
> hardened deployment would move to asymmetric signatures or online activation.
