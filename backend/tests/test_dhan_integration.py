"""LIVE mode end to end without real money.

A local HTTP server imitates the Dhan v2 order API. The real dhanhq SDK,
DhanClient and MirenExecutor run unmodified; only DHAN_API_BASE_URL points at
the mock (the same switch used for Dhan's sandbox).
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dhan_client import DhanClient, DhanError
from executor import MirenExecutor
from models import Action, EventKind, RegimeType
from tests.test_executor import ATR_FLAT, CALM_BUY, FakeDetector

CLIENT_ID = "1100000001"
TOKEN = "test-token"


class MockDhan:
    def __init__(self):
        self.requests: list[dict] = []
        self.mode = "fill"  # fill | partial | pending | reject | auth_error
        self.fill_price = 99.5
        self.orders: dict[str, dict] = {}


def make_server(state: MockDhan) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, code: int, body: object) -> None:
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _auth_ok(self) -> bool:
            if state.mode == "auth_error" or self.headers.get("access-token") != TOKEN:
                self._reply(401, {"errorType": "Invalid_Authentication", "errorCode": "DH-901", "errorMessage": "invalid token"})
                return False
            return True

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append({"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body})
            if not self._auth_ok():
                return
            oid = str(len(state.orders) + 1)
            status = "REJECTED" if state.mode == "reject" else "TRANSIT"
            order = {"orderId": oid, "orderStatus": status}
            if state.mode == "reject":
                order["omsErrorDescription"] = "RMS:Margin Exceeds"
            state.orders[oid] = {**body, **order, "filledQty": 0}
            self._reply(200, order)

        def do_DELETE(self):
            state.requests.append({"method": "DELETE", "path": self.path})
            if not self._auth_ok():
                return
            order = state.orders[self.path.rsplit("/", 1)[1]]
            order["orderStatus"] = "CANCELLED"
            order["cancelled"] = True
            self._reply(202, {"orderId": order["orderId"], "orderStatus": "CANCELLED"})

        def do_GET(self):
            state.requests.append({"method": "GET", "path": self.path})
            if not self._auth_ok():
                return
            order = state.orders.get(self.path.rsplit("/", 1)[1])
            if order is None:
                self._reply(404, {"errorType": "Order_Error", "errorCode": "DH-906", "errorMessage": "not found"})
                return
            if order.get("cancelled"):
                self._reply(200, order)
                return
            if state.mode == "fill":
                order.update(orderStatus="TRADED", averageTradedPrice=state.fill_price, filledQty=order["quantity"])
            elif state.mode == "partial":
                order.update(orderStatus="PART_TRADED", averageTradedPrice=state.fill_price, filledQty=order["quantity"] // 2)
            elif state.mode == "pending":
                order.update(orderStatus="PENDING")
            self._reply(200, order)

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


@pytest.fixture
def dhan(monkeypatch):
    state = MockDhan()
    server = make_server(state)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("DHAN_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", TOKEN)
    monkeypatch.setenv("DHAN_API_BASE_URL", f"http://127.0.0.1:{server.server_port}/v2")
    client = DhanClient()
    real_settle = client.settle
    client.settle = lambda oid: real_settle(oid, attempts=2, delay=0.01)  # type: ignore[method-assign]
    yield client, state
    server.shutdown()


def live(client, script):
    return MirenExecutor("RELIANCE.NS", 100_000, "LIVE", dhan_client=client, security_id="2885", detector=FakeDetector(script))


def test_order_payload_matches_dhan_v2(dhan):
    client, state = dhan
    client.place_order("2885", Action.BUY, 10, "MARKET", "NSE_EQ", "CNC", 0, "miren")
    req = state.requests[0]
    assert req["path"] == "/v2/orders"
    assert req["headers"]["access-token"] == TOKEN and req["headers"]["client-id"] == CLIENT_ID
    b = req["body"]
    assert (b["dhanClientId"], b["transactionType"], b["exchangeSegment"], b["productType"], b["orderType"]) == (
        CLIENT_ID, "BUY", "NSE_EQ", "CNC", "MARKET",
    )
    assert (b["securityId"], b["quantity"], b["validity"], b["correlationId"]) == ("2885", 10, "DAY", "miren")


async def test_live_round_trip_books_dhan_fill_price(dhan):
    client, state = dhan
    sell_bars = [100.0] * 15 + [101.0]  # CalmStrategy SELL
    ex = live(client, [(RegimeType.CALM, 0.9, CALM_BUY), (RegimeType.CALM, 0.9, sell_bars)])
    await ex.tick()
    assert ex.position_qty == 100_000 * 0.25 // 99.0 and ex.avg_price == 99.5
    await ex.tick()
    posts = [r["body"] for r in state.requests if r["method"] == "POST"]
    assert [p["transactionType"] for p in posts] == ["BUY", "SELL"]
    assert posts[1]["quantity"] == posts[0]["quantity"]
    assert ex.position_qty == 0 and ex.realized == 0  # both fills at the mock's 99.5
    assert [t.order_id for t in ex.trades] == ["1", "2"]


async def test_rejected_order_leaves_flat(dhan):
    client, state = dhan
    state.mode = "reject"
    ex = live(client, [(RegimeType.CALM, 0.9, CALM_BUY)])
    await ex.tick()
    assert ex.position_qty == 0
    assert "Margin Exceeds" in ex.events[0].message


async def test_partial_fill_keeps_filled_part_and_cancels_rest(dhan):
    client, state = dhan
    state.mode = "partial"
    ex = live(client, [(RegimeType.CALM, 0.9, CALM_BUY)])
    await ex.tick()
    ordered = state.orders["1"]["quantity"]
    assert ex.position_qty == ordered // 2
    assert any(r["method"] == "DELETE" for r in state.requests)
    assert any("rest was cancelled" in e.message for e in ex.events)


async def test_unfilled_order_is_cancelled_not_left_working(dhan):
    client, state = dhan
    state.mode = "pending"
    ex = live(client, [(RegimeType.CALM, 0.9, CALM_BUY)])
    await ex.tick()
    assert ex.position_qty == 0
    assert state.orders["1"]["orderStatus"] == "CANCELLED"
    assert ex.events[0].kind == EventKind.ERROR


async def test_expired_token_is_reported(dhan):
    client, state = dhan
    state.mode = "auth_error"
    with pytest.raises(DhanError):
        client.place_order("2885", Action.BUY, 1, "MARKET", "NSE_EQ", "CNC", 0, None)
    ex = live(client, [(RegimeType.VOLATILE, 0.9, ATR_FLAT + [110.0])])
    await ex.tick()
    assert ex.position_qty == 0 and ex.events[0].kind == EventKind.ERROR
