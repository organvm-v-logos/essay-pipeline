# ADR 003: Template Library Licensing

## Status

Accepted

## Date

2026-06-19

> Update, 2026-06-20: ADR 004 adds Stripe Checkout and optional subscription
> issuance. This ADR remains the decision record for the offline license gate
> that premium features consume.

## Context

The essay-pipeline already enforces a strict frontmatter schema on every essay
it publishes (see ADR 002). That schema is, in effect, a structural contract:
a known-good shape that a draft must satisfy. We can package that contract as a
product — a catalog of ready-to-fill **schema-enforced templates** that drop an
author straight into a valid scaffold.

The product started as a **one-time-purchase template library** ($49 single
template, $99 full bundle): a free sample template plus a set of premium
templates behind a license gate. We need to decide how that gate works, given
hard constraints:

1. No user accounts, and no requirement that reads call back to a hosted
   activation service. Optional subscription billing can still issue expiring
   offline keys.
2. No activation/license server to run and keep available — the pipeline is a
   set of CLI tools and GitHub Actions, not a hosted service.
3. The whole repo is open source, so the gate must be honest about what it can
   and cannot enforce.
4. Issuing a key after a sale must be a single command the seller can run.

### Options

**Option A: HMAC-signed offline keys (chosen)**
A license key is a readable payload (`sku | email | issued | optional expires`)
plus a truncated HMAC-SHA256 tag, base32-encoded. The same shared secret signs
and verifies, so verification is fully offline. Issuing is one command;
checking is one function.

**Option B: Asymmetric signatures (Ed25519)**
The seller holds a private key; the client ships only the public key. A leaked
client cannot mint keys. Strictly stronger than HMAC, but adds a crypto
dependency and key-management ceremony that is overkill for a deterrent-grade
gate on an open-source repo where the templates are readable in git history
anyway.

**Option C: Online activation**
A hosted endpoint validates keys and can revoke them. Strongest control, but
violates constraints 2 and contradicts the "invisible infrastructure, no server"
posture of the pipeline.

**Option D: Honor-system / paywall copy**
Just ask people to pay. Zero engineering, zero enforcement. Rejected because the
task explicitly calls for an HMAC key check.

## Decision

Adopt **Option A**. Implement license issuance/verification in
[`src/license.py`](../../src/license.py) and gate premium template reads in
[`src/template_store.py`](../../src/template_store.py) behind
`verify_license()`. The catalog lives in
[`templates/manifest.yaml`](../../templates/manifest.yaml); free templates are
served unconditionally, premium templates require a license whose `sku` covers
premium access.

Key format: `EPK1.<base32 payload>.<base32 tag>`. The payload is intentionally
*readable* (a license should disclose who/what/when, and possibly until when),
only signed — not encrypted. The signing secret resolves from
`ESSAY_PIPELINE_LICENSE_SECRET`, falling back to a bundled demo secret so the
gate is exercisable in tests and CI without configuration.

## Consequences

- **Positive.** No server, no accounts, no dependencies beyond the standard
  library (`hmac`, `hashlib`, `base64`). Issuing a key is one CLI command.
  Verification is deterministic and unit-testable. The gate cleanly separates
  the free sample from the paid set.
- **Negative / accepted risk.** This is a *deterrent*, not DRM. The shared
  secret must ship wherever verification happens, so anyone with the secret —
  or willing to edit the open-source verifier — can bypass the gate. The
  templates themselves are visible in git history. We accept this: the product
  is convenience and curation, not secrecy. If the secret leaks, rotate it and
  re-issue keys.
- **Migration path.** If stronger enforcement is ever needed, swap the HMAC
  check in `src/license.py` for Ed25519 (Option B) or add an online activation
  call (Option C) without touching the storefront in `src/template_store.py`.
