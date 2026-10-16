"""Walks one order through Miren's Dhan client on the Dhan sandbox (virtual money).

Usage, from backend/:  .venv/bin/python scripts/dhan_sandbox_check.py

Needs DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN and DHAN_API_BASE_URL=https://sandbox.dhan.co/v2
in .env (sandbox keys from developer.dhanhq.co). Refuses to run against any other URL,
so it can never touch real money.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND.parent / ".env")
load_dotenv(BACKEND / ".env")

from dhan_client import DhanClient, DhanError  # noqa: E402
from models import Action  # noqa: E402

SECURITY_ID = "2885"  # RELIANCE, NSE_EQ


def main() -> int:
    client = DhanClient()
    if not client.configured:
        print("FAIL  DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN are not set in .env")
        return 1
    if not client.base_url.startswith("https://sandbox.dhan.co/"):
        print("STOP  DHAN_API_BASE_URL is not https://sandbox.dhan.co/v2; refusing to place an order")
        return 1
    print(f"Using {client.base_url} (sandbox, virtual money)")

    try:
        positions = client.get_positions()
        print(f"OK    auth works, {len(positions)} open position(s)")

        # the same call shape the executor uses in LIVE mode
        resp = client.place_order(SECURITY_ID, Action.BUY, 1, "MARKET", "NSE_EQ", "CNC", 0, "miren-sandbox")
        order_id = str(resp["orderId"])
        print(f"OK    BUY accepted: id {order_id}, status {resp.get('orderStatus')}")
        status, price, qty = client.settle(order_id, attempts=10, delay=1.0)
        print(f"OK    BUY settled {status}, filled {qty} @ {price}")

        if qty > 0:
            sell = client.place_order(SECURITY_ID, Action.SELL, qty, "MARKET", "NSE_EQ", "CNC", 0, "miren-sandbox")
            s_status, s_price, s_qty = client.settle(str(sell["orderId"]), attempts=10, delay=1.0)
            print(f"OK    SELL settled {s_status}, filled {s_qty} @ {s_price}")
    except DhanError as exc:
        print(f"FAIL  {exc}")
        return 1
    print("PASS  Dhan sandbox round trip works through Miren's client")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
