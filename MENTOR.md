# Note for a Bitrefill mentor — test delivery failing on our account

**Account:** shayans210@gmail.com (Personal API key)
**Date:** 2026-06-17
**Symptom:** Orders that delivered fine earlier today now return
`status: permanent_failure` (`invoice` rollup `all_error` / `not_delivered`),
with the balance auto-refunded. Affects **both** test products and real products,
on the **balance** payment path.

## Evidence (same account, ~20 min apart)

| Time (UTC) | Action | Result |
| --- | --- | --- |
| 13:33:56–59 | `delos-syldavia` ×3, `payment_method=balance`, `auto_pay` (invoice `ca7c61cd-00ec-4bf1-97fd-75e277eeaddf`) | **all delivered**, real codes, `delivered_time` set |
| 13:55:52 | `delos-syldavia` ×1, same params (invoice `495aa1a6-494f-4318-abec-16e9cf09a68d`) | **permanent_failure**, `delivered_time: null` |
| ~13:5x | real NG gift cards `spar-market-nigeria`, `sufi-mart-nigeria` from balance | **permanent_failure**, debited €0.66 then auto-refunded to €20.00 |
| later | `test-gift-card-code` (value 10), `mobile-legends-international` (cheapest) from balance | **permanent_failure** |

The failing order object carries **no `error`/`message`** — just
`status: permanent_failure`, `delivered_time: null`. Example failed order id:
`6a32a768c80748b7df3a5e2c`.

Crypto-path test invoices (e.g. `usdc_base`, `return_payment_link`) sit at order
`status: created` / invoice `not_delivered` and never auto-deliver either.

## What we've ruled out
- **Not our code:** the identical call path delivered at 13:33 and failed at 13:55;
  nothing on our side changed between runs.
- **Not balance/credit:** the €20 test credits read fine (`{"balance":2000,"currency":"EUR"}`)
  and failed charges refund correctly.
- **Not a polling bug:** we settle on per-order `status` (per your testing guide),
  not the top-level rollup, and we see the terminal `permanent_failure` immediately.

## Questions for you
1. Is test/voucher **delivery** currently degraded for our account (or globally)?
2. Did our account hit a per-day test-delivery quota or get a delivery flag toggled
   around **13:34–13:55 UTC** today?
3. Anything we should change for the `balance` path beyond
   `payment_method=balance` + `auto_pay=true` on `POST /v2/invoices`?

Happy to share any invoice/order ids above.
