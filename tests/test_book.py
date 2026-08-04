import unittest
from decimal import Decimal as D

from book import Book


class TestCashEvents(unittest.TestCase):

    def test_deposit(self):
        book = Book()

        legs = book.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "1000.00",
            },
        })

        self.assertEqual(len(legs), 2)

        snapshot = book.snapshot()

        self.assertEqual(
            snapshot["customers"]["C1"]["wallet_cash"],
            "1000.00",
        )

    def test_fee_charged(self):
        book = Book()

        book.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "1000.00",
            },
        })

        book.apply({
            "event_id": "fee-1",
            "type": "fee_charged",
            "payload": {
                "customer_id": "C1",
                "amount": "25.50",
            },
        })

        snapshot = book.snapshot()

        self.assertEqual(
            snapshot["customers"]["C1"]["wallet_cash"],
            "974.50",
        )

    def test_fee_refund(self):
        book = Book()

        book.apply({
            "event_id": "fee-1",
            "type": "fee_charged",
            "payload": {
                "customer_id": "C1",
                "amount": "25.50",
            },
        })

        book.apply({
            "event_id": "refund-1",
            "type": "fee_refund",
            "payload": {
                "customer_id": "C1",
                "refunds_source_id": "fee-1",
            },
        })

        snapshot = book.snapshot()

        self.assertEqual(
            snapshot["customers"]["C1"]["wallet_cash"],
            "0.00",
        )

    def test_duplicate_fee_refund_is_rejected(self):
        book = Book()

        book.apply({
            "event_id": "fee-1",
            "type": "fee_charged",
            "payload": {
                "customer_id": "C1",
                "amount": "25.50",
            },
        })

        book.apply({
            "event_id": "refund-1",
            "type": "fee_refund",
            "payload": {
                "customer_id": "C1",
                "refunds_source_id": "fee-1",
            },
        })

        legs = book.apply({
            "event_id": "refund-2",
            "type": "fee_refund",
            "payload": {
                "customer_id": "C1",
                "refunds_source_id": "fee-1",
            },
        })

        self.assertEqual(legs, [])

    def test_withdrawal_settled(self):
        book = Book()

        book.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "1000.00",
            },
        })

        book.apply({
            "event_id": "wr-1",
            "type": "withdrawal_requested",
            "payload": {
                "withdrawal_id": "W1",
                "customer_id": "C1",
                "amount": "250.00",
            },
        })

        book.apply({
            "event_id": "ws-1",
            "type": "withdrawal_settled",
            "payload": {
                "withdrawal_id": "W1",
            },
        })

        snapshot = book.snapshot()

        self.assertEqual(
            snapshot["customers"]["C1"]["wallet_cash"],
            "750.00",
        )

        self.assertEqual(
            snapshot["trial_balance"]["2300"],
            "0.00",
        )

    def test_withdrawal_rejected(self):
        book = Book()

        book.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "1000.00",
            },
        })

        book.apply({
            "event_id": "wr-1",
            "type": "withdrawal_requested",
            "payload": {
                "withdrawal_id": "W1",
                "customer_id": "C1",
                "amount": "250.00",
            },
        })

        book.apply({
            "event_id": "wj-1",
            "type": "withdrawal_rejected",
            "payload": {
                "withdrawal_id": "W1",
            },
        })

        snapshot = book.snapshot()

        self.assertEqual(
            snapshot["customers"]["C1"]["wallet_cash"],
            "1000.00",
        )

    def test_interest_credited(self):
        book = Book()

        legs = book.apply({
            "event_id": "i1",
            "type": "interest_credited",
            "payload": {
                "customer_id": "C1",
                "gross_amount": "50.00",
                "customer_share": "40.00",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "50.00",
                    "credit": "0.00",
                },
                {
                    "account": "2010",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "40.00",
                },
                {
                    "account": "4200",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "10.00",
                },
            ],
        )

        snapshot = book.snapshot()

        self.assertEqual(
            snapshot["customers"]["C1"]["wallet_cash"],
            "40.00",
        )

        self.assertEqual(
            snapshot["trial_balance"]["4200"],
            "-10.00",
        )

    def test_transfer_between_customers(self):
        book = Book()

        book.apply({
            "event_id": "d1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "1000.00",
            },
        })

        book.apply({
            "event_id": "t1",
            "type": "transfer_between_customers",
            "payload": {
                "from_customer_id": "C1",
                "to_customer_id": "C2",
                "amount": "300.00",
            },
        })

        snapshot = book.snapshot()

        self.assertEqual(
            snapshot["customers"]["C1"]["wallet_cash"],
            "700.00",
        )

        self.assertEqual(
            snapshot["customers"]["C2"]["wallet_cash"],
            "300.00",
        )

    def test_fx_deposit(self):
        book = Book()

        book.apply({
            "event_id": "fx1",
            "type": "fx_deposit",
            "payload": {
                "customer_id": "C1",
                "currency": "EUR",
                "amount_foreign": "100.00",
                "market_rate": "1.10",
                "customer_rate": "1.08",
                "usd_at_market_rate": "110.00",
                "usd_at_customer_rate": "108.00",
            },
        })

        snapshot = book.snapshot()

        self.assertEqual(
            snapshot["customers"]["C1"]["wallet_cash"],
            "108.00",
        )

        self.assertEqual(
            snapshot["trial_balance"]["4100"],
            "-2.00",
        )

    def test_invalid_fx_is_rejected_without_state_change(self):
        book = Book()

        legs = book.apply({
            "event_id": "bad-fx",
            "type": "fx_deposit",
            "payload": {
                "customer_id": "C1",
                "currency": "EUR",
                "amount_foreign": "100.00",
                "market_rate": "1.08",
                "customer_rate": "1.10",
                "usd_at_market_rate": "108.00",
                "usd_at_customer_rate": "110.00",
            },
        })

        self.assertEqual(legs, [])
        self.assertEqual(
            book.snapshot(),
            {
                "trial_balance": {},
                "customers": {},
            },
        )

class TestBuyOrderLifecycle(unittest.TestCase):

    def _place_buy(self, book):
        return book.apply({
            "event_id": "o1",
            "type": "order_placed",
            "payload": {
                "order_id": "ORD1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "10",
                "limit_price": "100.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

    def test_buy_order_creates_cash_hold_without_legs(self):
        book = Book()

        legs = self._place_buy(book)

        self.assertEqual(legs, [])
        self.assertEqual(
            book.snapshot()["customers"]["C1"]["cash_hold"],
            "1010.00",
        )
        self.assertEqual(
            book.orders["ORD1"]["remaining_quantity"],
            book.orders["ORD1"]["quantity"],
        )
        self.assertEqual(book.orders["ORD1"]["status"], "open")

    def test_cancelled_buy_releases_hold(self):
        book = Book()
        self._place_buy(book)

        legs = book.apply({
            "event_id": "c1",
            "type": "order_cancelled",
            "payload": {
                "order_id": "ORD1",
            },
        })

        self.assertEqual(legs, [])
        self.assertEqual(
            book.snapshot()["customers"]["C1"]["cash_hold"],
            "0.00",
        )

    def test_rejected_buy_releases_hold(self):
        book = Book()
        self._place_buy(book)

        legs = book.apply({
            "event_id": "r1",
            "type": "order_rejected",
            "payload": {
                "order_id": "ORD1",
            },
        })

        self.assertEqual(legs, [])
        self.assertEqual(
            book.snapshot()["customers"]["C1"]["cash_hold"],
            "0.00",
        )

    def test_partial_buy_releases_proportional_hold(self):
        book = Book()
        self._place_buy(book)

        book.apply({
            "event_id": "pf1",
            "type": "order_partially_filled",
            "payload": {
                "order_id": "ORD1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "4",
                "price": "100.00",
                "principal": "400.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T1",
            },
        })

        order = book.orders["ORD1"]

        self.assertEqual(str(order["remaining_quantity"]), "6")
        self.assertEqual(
            str(order["remaining_cash_hold"]),
            "606.00",
        )
        self.assertEqual(order["status"], "open")

    def test_partial_then_final_buy_closes_order(self):
        book = Book()

        book.apply({
            "event_id": "d1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "2000.00",
            },
        })

        self._place_buy(book)

        book.apply({
            "event_id": "pf1",
            "type": "order_partially_filled",
            "payload": {
                "order_id": "ORD1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "4",
                "price": "100.00",
                "principal": "400.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T1",
            },
        })

        book.apply({
            "event_id": "f2",
            "type": "order_filled",
            "payload": {
                "order_id": "ORD1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "6",
                "price": "100.00",
                "principal": "600.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T2",
            },
        })

        order = book.orders["ORD1"]
        snapshot = book.snapshot()

        self.assertEqual(str(order["remaining_quantity"]), "0.00")
        self.assertEqual(
            str(order["remaining_cash_hold"]),
            "0.00",
        )
        self.assertEqual(order["status"], "filled")
        self.assertEqual(
            snapshot["customers"]["C1"]["cash_hold"],
            "0.00",
        )
        self.assertEqual(
            snapshot["customers"]["C1"]["wallet_cash"],
            "996.60",
        )

    def test_partial_and_final_buy_create_separate_fifo_lots(self):
        b = Book()

        b.apply({
            "event_id": "o1",
            "type": "order_placed",
            "payload": {
                "order_id": "ORD1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "10",
                "limit_price": "100.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        b.apply({
            "event_id": "pf1",
            "type": "order_partially_filled",
            "payload": {
                "order_id": "ORD1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "4",
                "price": "100.00",
                "principal": "400.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T1",
            },
        })

        b.apply({
            "event_id": "f2",
            "type": "order_filled",
            "payload": {
                "order_id": "ORD1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "6",
                "price": "100.00",
                "principal": "600.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T2",
            },
        })

        lots = b.lots[("C1", "ACME")]

        self.assertEqual(len(lots), 2)

        self.assertEqual(lots[0]["trade_id"], "T1")
        self.assertEqual(lots[0]["quantity"], D("4"))
        self.assertEqual(lots[0]["cost"], D("400.00"))

        self.assertEqual(lots[1]["trade_id"], "T2")
        self.assertEqual(lots[1]["quantity"], D("6"))
        self.assertEqual(lots[1]["cost"], D("600.00"))


    def test_buy_lots_are_reported_as_position(self):
        b = Book()

        b.apply({
            "event_id": "o1",
            "type": "order_placed",
            "payload": {
                "order_id": "ORD1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "10",
                "limit_price": "100.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        b.apply({
            "event_id": "f1",
            "type": "order_filled",
            "payload": {
                "order_id": "ORD1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "10",
                "price": "100.00",
                "principal": "1000.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T1",
            },
        })

        position = b.snapshot()["customers"]["C1"]["positions"]["ACME"]

        self.assertEqual(D(position["quantity"]), D("10"))
        self.assertEqual(D(position["cost_basis"]), D("1000.00"))

class TestSellOrderLifecycle(unittest.TestCase):

    def _book_with_position(self):
        b = Book()

        b.apply({
            "event_id": "buy-order",
            "type": "order_placed",
            "payload": {
                "order_id": "BUY1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "10",
                "limit_price": "100.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        b.apply({
            "event_id": "buy-fill",
            "type": "order_filled",
            "payload": {
                "order_id": "BUY1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "10",
                "price": "100.00",
                "principal": "1000.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T-BUY",
            },
        })

        return b

    def _place_sell(self, b, event_id="s1",
                    order_id="SELL1", quantity="7"):
        return b.apply({
            "event_id": event_id,
            "type": "order_placed",
            "payload": {
                "order_id": order_id,
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": quantity,
                "limit_price": "110.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

    def test_sell_order_holds_owned_shares(self):
        b = self._book_with_position()

        legs = self._place_sell(b)

        self.assertEqual(legs, [])
        self.assertEqual(
            b._owned_quantity("C1", "ACME"),
            D("10"),
        )
        self.assertEqual(
            b._share_hold("C1", "ACME"),
            D("7"),
        )

        order = b.orders["SELL1"]

        self.assertEqual(
            order["remaining_quantity"],
            D("7"),
        )
        self.assertEqual(order["status"], "open")

    def test_second_sell_cannot_exceed_available_shares(self):
        b = self._book_with_position()

        self._place_sell(
            b,
            event_id="s1",
            order_id="SELL1",
            quantity="7",
        )

        legs = self._place_sell(
            b,
            event_id="s2",
            order_id="SELL2",
            quantity="4",
        )

        self.assertEqual(legs, [])

        # Rejected event must not create the second order.
        self.assertNotIn("SELL2", b.orders)

        self.assertEqual(
            b._share_hold("C1", "ACME"),
            D("7"),
        )

        # Placement/failed oversell must not consume the position.
        position = (
            b.snapshot()["customers"]["C1"]
            ["positions"]["ACME"]
        )

        self.assertEqual(
            D(position["quantity"]),
            D("10"),
        )

    def test_cancelled_sell_releases_share_hold(self):
        b = self._book_with_position()

        self._place_sell(
            b,
            event_id="s1",
            order_id="SELL1",
            quantity="7",
        )

        b.apply({
            "event_id": "cancel-1",
            "type": "order_cancelled",
            "payload": {
                "order_id": "SELL1",
            },
        })

        self.assertEqual(
            b._share_hold("C1", "ACME"),
            D("0"),
        )

        legs = self._place_sell(
            b,
            event_id="s2",
            order_id="SELL2",
            quantity="10",
        )

        self.assertEqual(legs, [])
        self.assertIn("SELL2", b.orders)
        self.assertEqual(
            b._share_hold("C1", "ACME"),
            D("10"),
        )

if __name__ == "__main__":
    unittest.main()