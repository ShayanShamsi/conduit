"""Live-debit demo — a REAL autonomous purchase with a visible balance drop.

Buys the cheapest Mobile Legends Diamonds (~$0.18, no recipient needed) from the
account balance and prints balance before/after so you can see real money move.
This proves the production account-balance checkout, not a free test product.

    uv run python -m bitrefill_agent.demo_live

Uses the provisioned test credits (balance is EUR minor units; 2000 = €20.00).
"""

from __future__ import annotations

import time

from .catalog import get_product
from .client import BitrefillClient
from .purchase import buy_basket, mask_code

PRODUCT = "mobile-legends-international"


def main() -> None:
    with BitrefillClient() as bf:
        product = get_product(bf, PRODUCT)
        cheapest = min(product["packages"], key=lambda p: float(p.get("price", 1e9)))
        print(f"Product : {product['name']}")
        print(f"Buying  : {cheapest['value']}  (~${cheapest['price']})  paid from balance\n")

        before = bf.balance()
        print(f"balance before: {before['balance']} {before['currency']} (minor units)")

        receipt = buy_basket(
            bf,
            [{"product_id": PRODUCT, "package_id": cheapest["id"], "quantity": 1}],
            payment_method="balance",
        )
        o = receipt.outcomes[0] if receipt.outcomes else None
        status = o.status if o else "no-order"
        print(f"checkout: invoice {receipt.invoice_id} | order {status} | code {mask_code(o.redemption_info if o else None)}")

        time.sleep(3)  # let balance settle (failed orders auto-refund)
        after = bf.balance()
        delta = before["balance"] - after["balance"]
        print(f"balance after : {after['balance']} {after['currency']}")
        if delta > 0:
            print(f"✅ debited {delta} {after['currency']} minor units — real autonomous purchase, no human in the loop.")
        elif status == "delivered":
            print("✅ delivered (debit may lag a moment).")
        else:
            print("⚠️  order not delivered — auto-refunded, so balance is unchanged "
                  "(Bitrefill's delivery rail may be degraded; retry when healthy).")


if __name__ == "__main__":
    main()
