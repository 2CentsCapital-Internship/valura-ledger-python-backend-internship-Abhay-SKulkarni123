import unittest
from decimal import Decimal as D

from book import Book, Rejected


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

    def test_fifo_consumes_oldest_lots_first(self):
        b = Book()

        b.lots[("C1", "ACME")].append({
            "event_id": "buy-1",
            "trade_id": "T1",
            "quantity": D("4"),
            "cost": D("400.00"),
        })

        b.lots[("C1", "ACME")].append({
            "event_id": "buy-2",
            "trade_id": "T2",
            "quantity": D("6"),
            "cost": D("600.00"),
        })

        cost = b._consume_fifo(
            "C1",
            "ACME",
            D("7"),
        )

        self.assertEqual(cost, D("700.00"))

        lots = b.lots[("C1", "ACME")]

        self.assertEqual(len(lots), 1)

        self.assertEqual(
            lots[0]["trade_id"],
            "T2",
        )

        self.assertEqual(
            lots[0]["quantity"],
            D("3"),
        )

        self.assertEqual(
            lots[0]["cost"],
            D("300.00"),
        )

        position = (
            b.snapshot()["customers"]["C1"]
            ["positions"]["ACME"]
        )

        self.assertEqual(
            D(position["quantity"]),
            D("3"),
        )

        self.assertEqual(
            D(position["cost_basis"]),
            D("300.00"),
        )

    def test_fifo_partial_lot_uses_total_cost_rounding(self):
        b = Book()

        b.lots[("C1", "ACME")].append({
            "event_id": "buy-1",
            "trade_id": "T1",
            "quantity": D("10"),
            "cost": D("100.03"),
        })

        cost = b._consume_fifo(
            "C1",
            "ACME",
            D("3"),
        )

        self.assertEqual(
            cost,
            D("30.01"),
        )

        lot = b.lots[("C1", "ACME")][0]

        self.assertEqual(
            lot["quantity"],
            D("7"),
        )

        self.assertEqual(
            lot["cost"],
            D("70.02"),
        )

    def test_full_sell_consumes_fifo_and_closes_order(self):
        b = self._book_with_position()

        self._place_sell(
            b,
            event_id="s1",
            order_id="SELL1",
            quantity="7",
        )

        legs = b.apply({
            "event_id": "sf1",
            "type": "order_filled",
            "payload": {
                "order_id": "SELL1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "7",
                "price": "120.00",
                "principal": "840.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T-SELL-1",
            },
        })

        self.assertTrue(legs)

        order = b.orders["SELL1"]

        self.assertEqual(
            order["remaining_quantity"],
            D("0"),
        )
        self.assertEqual(order["status"], "filled")

        self.assertEqual(
            b._share_hold("C1", "ACME"),
            D("0"),
        )

        position = (
            b.snapshot()["customers"]["C1"]
            ["positions"]["ACME"]
        )

        self.assertEqual(
            D(position["quantity"]),
            D("3"),
        )

        self.assertEqual(
            D(position["cost_basis"]),
            D("300.00"),
        )

    def test_partial_then_final_sell_updates_hold_and_position(self):
        b = self._book_with_position()

        self._place_sell(
            b,
            event_id="s1",
            order_id="SELL1",
            quantity="7",
        )

        b.apply({
            "event_id": "sp1",
            "type": "order_partially_filled",
            "payload": {
                "order_id": "SELL1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "4",
                "price": "120.00",
                "principal": "480.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T-SELL-1",
            },
        })

        self.assertEqual(
            b.orders["SELL1"]["remaining_quantity"],
            D("3"),
        )

        self.assertEqual(
            b.orders["SELL1"]["status"],
            "open",
        )

        self.assertEqual(
            b._share_hold("C1", "ACME"),
            D("3"),
        )

        position = (
            b.snapshot()["customers"]["C1"]
            ["positions"]["ACME"]
        )

        self.assertEqual(
            D(position["quantity"]),
            D("6"),
        )

        self.assertEqual(
            D(position["cost_basis"]),
            D("600.00"),
        )

        b.apply({
            "event_id": "sf1",
            "type": "order_filled",
            "payload": {
                "order_id": "SELL1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "3",
                "price": "125.00",
                "principal": "375.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T-SELL-2",
            },
        })

        self.assertEqual(
            b.orders["SELL1"]["remaining_quantity"],
            D("0"),
        )

        self.assertEqual(
            b.orders["SELL1"]["status"],
            "filled",
        )

        self.assertEqual(
            b._share_hold("C1", "ACME"),
            D("0"),
        )

        position = (
            b.snapshot()["customers"]["C1"]
            ["positions"]["ACME"]
        )

        self.assertEqual(
            D(position["quantity"]),
            D("3"),
        )

        self.assertEqual(
            D(position["cost_basis"]),
            D("300.00"),
        )

    def test_sell_across_multiple_lots_uses_fifo_cost(self):
        b = Book()

        # Oldest lot: 4 shares costing 400 total.
        b.lots[("C1", "ACME")].append({
            "event_id": "buy-1",
            "trade_id": "T-BUY-1",
            "quantity": D("4"),
            "cost": D("400.00"),
        })

        # Newer lot: 6 shares costing 720 total.
        b.lots[("C1", "ACME")].append({
            "event_id": "buy-2",
            "trade_id": "T-BUY-2",
            "quantity": D("6"),
            "cost": D("720.00"),
        })

        # Sell 7 of the 10 shares.
        b.apply({
            "event_id": "sell-order",
            "type": "order_placed",
            "payload": {
                "order_id": "SELL1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "7",
                "limit_price": "150.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        legs = b.apply({
            "event_id": "sell-fill",
            "type": "order_filled",
            "payload": {
                "order_id": "SELL1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "7",
                "price": "150.00",
                "principal": "1050.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T-SELL-1",
            },
        })

        self.assertTrue(legs)

        # FIFO:
        # first 4 shares consume all $400 of lot 1
        # next 3 consume 3/6 of $720 = $360
        # total FIFO cost relieved = $760
        #
        # Remaining lot:
        # 3 shares / $360
        lots = b.lots[("C1", "ACME")]

        self.assertEqual(len(lots), 1)
        self.assertEqual(
            lots[0]["trade_id"],
            "T-BUY-2",
        )
        self.assertEqual(
            lots[0]["quantity"],
            D("3"),
        )
        self.assertEqual(
            lots[0]["cost"],
            D("360.00"),
        )

        position = (
            b.snapshot()["customers"]["C1"]
            ["positions"]["ACME"]
        )

        self.assertEqual(
            D(position["quantity"]),
            D("3"),
        )
        self.assertEqual(
            D(position["cost_basis"]),
            D("360.00"),
        )

        self.assertEqual(
            b.orders["SELL1"]["status"],
            "filled",
        )

    def test_rejected_sell_fill_does_not_mutate_lots_or_order(self):
        b = self._book_with_position()

        self._place_sell(
            b,
            event_id="s1",
            order_id="SELL1",
            quantity="7",
        )

        lots_before = [
            {
                "event_id": lot["event_id"],
                "trade_id": lot["trade_id"],
                "quantity": lot["quantity"],
                "cost": lot["cost"],
            }
            for lot in b.lots[("C1", "ACME")]
        ]

        # Final fill must equal the remaining order quantity.
        # SELL1 has 7 remaining, so a final fill of 8 is invalid.
        legs = b.apply({
            "event_id": "bad-fill",
            "type": "order_filled",
            "payload": {
                "order_id": "SELL1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "8",
                "price": "120.00",
                "principal": "960.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T-BAD",
            },
        })

        self.assertEqual(legs, [])

        # FIFO lots must be untouched.
        self.assertEqual(
            b.lots[("C1", "ACME")],
            lots_before,
        )

        # Original SELL order must still be open and unchanged.
        order = b.orders["SELL1"]

        self.assertEqual(
            order["remaining_quantity"],
            D("7"),
        )
        self.assertEqual(
            order["status"],
            "open",
        )

        self.assertEqual(
            b._share_hold("C1", "ACME"),
            D("7"),
        )

        position = (
            b.snapshot()["customers"]["C1"]
            ["positions"]["ACME"]
        )

        self.assertEqual(
            D(position["quantity"]),
            D("10"),
        )
        self.assertEqual(
            D(position["cost_basis"]),
            D("1000.00"),
        )

class TestTradeAccounting(unittest.TestCase):

    def test_trade_fee_calculation_exact_amounts(self):
        b = Book()

        fees = b._trade_fees(
            "1000.00",
            "BRK-A",
            "0.50",
        )

        self.assertEqual(
            fees["brokerage"],
            D("2.00"),
        )
        self.assertEqual(
            fees["custody"],
            D("0.40"),
        )
        self.assertEqual(
            fees["regulatory"],
            D("0.80"),
        )
        self.assertEqual(
            fees["broker_cost"],
            D("1.25"),
        )
        self.assertEqual(
            fees["custody_cost"],
            D("0.20"),
        )
        self.assertEqual(
            fees["partner_share"],
            D("0.48"),
        )
        self.assertEqual(
            fees["broker_payable_account"],
            "2411",
        )


    def test_buy_fill_has_exact_balanced_journal(self):
        b = Book()

        payload = {
            "customer_id": "C1",
            "principal": "1000.00",
            "broker": "BRK-A",
            "partner_rate": "0.50",
        }

        legs = b._buy_fill_legs(payload)

        expected = [
            {
                "account": "2010",
                "customer_id": "C1",
                "debit": "1003.20",
                "credit": "0.00",
            },
            {
                "account": "2350",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "1000.00",
            },
            {
                "account": "1200",
                "customer_id": "C1",
                "debit": "1000.00",
                "credit": "0.00",
            },
            {
                "account": "2100",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "1000.00",
            },
            {
                "account": "5000",
                "customer_id": "C1",
                "debit": "1.25",
                "credit": "0.00",
            },
            {
                "account": "4000",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "2.00",
            },
            {
                "account": "5010",
                "customer_id": "C1",
                "debit": "0.20",
                "credit": "0.00",
            },
            {
                "account": "4010",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "0.40",
            },
            {
                "account": "5100",
                "customer_id": "C1",
                "debit": "0.48",
                "credit": "0.00",
            },
            {
                "account": "2400",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "0.80",
            },
            {
                "account": "2411",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "1.25",
            },
            {
                "account": "2420",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "0.20",
            },
            {
                "account": "2430",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "0.48",
            },
        ]

        self.assertEqual(legs, expected)

        total_debits = sum(
            D(item["debit"])
            for item in legs
        )

        total_credits = sum(
            D(item["credit"])
            for item in legs
        )

        self.assertEqual(
            total_debits,
            total_credits,
        )


    def test_sell_fill_has_exact_balanced_journal(self):
        b = Book()

        payload = {
            "customer_id": "C1",
            "principal": "1000.00",
            "broker": "BRK-A",
            "partner_rate": "0.50",
        }

        legs = b._sell_fill_legs(
            payload,
            D("700.00"),
        )

        expected = [
            {
                "account": "1150",
                "customer_id": "C1",
                "debit": "1000.00",
                "credit": "0.00",
            },
            {
                "account": "2010",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "996.80",
            },
            {
                "account": "2100",
                "customer_id": "C1",
                "debit": "700.00",
                "credit": "0.00",
            },
            {
                "account": "1200",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "700.00",
            },
            {
                "account": "5000",
                "customer_id": "C1",
                "debit": "1.25",
                "credit": "0.00",
            },
            {
                "account": "4000",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "2.00",
            },
            {
                "account": "5010",
                "customer_id": "C1",
                "debit": "0.20",
                "credit": "0.00",
            },
            {
                "account": "4010",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "0.40",
            },
            {
                "account": "5100",
                "customer_id": "C1",
                "debit": "0.48",
                "credit": "0.00",
            },
            {
                "account": "2400",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "0.80",
            },
            {
                "account": "2411",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "1.25",
            },
            {
                "account": "2420",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "0.20",
            },
            {
                "account": "2430",
                "customer_id": "C1",
                "debit": "0.00",
                "credit": "0.48",
            },
        ]

        self.assertEqual(legs, expected)

        total_debits = sum(
            D(item["debit"])
            for item in legs
        )

        total_credits = sum(
            D(item["credit"])
            for item in legs
        )

        self.assertEqual(
            total_debits,
            total_credits,
        )

    def test_partner_share_is_zero_when_trade_margin_is_negative(self):
        b = Book()

        fees = b._trade_fees(
            "10.00",
            "BRK-B",
            "0.50",
        )

        self.assertEqual(
            fees["brokerage"],
            D("2.50"),
        )

        self.assertEqual(
            fees["broker_cost"],
            D("3.01"),
        )

        self.assertEqual(
            fees["partner_share"],
            D("0.00"),
        )

class TestTradeSettlement(unittest.TestCase):

    def _filled_buy(self):
        b = Book()

        b.apply({
            "event_id": "d1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "2000.00",
            },
        })

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

        return b


    def test_buy_trade_settlement_clears_broker_payable(self):
        b = self._filled_buy()

        legs = b.apply({
            "event_id": "st1",
            "type": "trade_settled",
            "payload": {
                "trade_id": "T1",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "2350",
                    "customer_id": "C1",
                    "debit": "1000.00",
                    "credit": "0.00",
                },
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "1000.00",
                },
            ],
        )

        self.assertTrue(
            b.trades["T1"]["settled"]
        )

        self.assertEqual(
            b.snapshot()["trial_balance"]["2350"],
            "0.00",
        )


    def test_duplicate_trade_settlement_is_rejected(self):
        b = self._filled_buy()

        first = b.apply({
            "event_id": "st1",
            "type": "trade_settled",
            "payload": {
                "trade_id": "T1",
            },
        })

        self.assertTrue(first)

        snapshot_before = b.snapshot()

        second = b.apply({
            "event_id": "st2",
            "type": "trade_settled",
            "payload": {
                "trade_id": "T1",
            },
        })

        self.assertEqual(second, [])
        self.assertEqual(
            b.snapshot(),
            snapshot_before,
        )


    def test_unknown_trade_settlement_is_rejected(self):
        b = Book()

        before = b.snapshot()

        legs = b.apply({
            "event_id": "st1",
            "type": "trade_settled",
            "payload": {
                "trade_id": "DOES-NOT-EXIST",
            },
        })

        self.assertEqual(legs, [])
        self.assertEqual(
            b.snapshot(),
            before,
        )

    def test_sell_trade_settlement_clears_broker_receivable(self):
        b = Book()

        # Create inventory through a completed BUY.
        b.apply({
            "event_id": "bo1",
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
            "event_id": "bf1",
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
                "trade_id": "BUY-T1",
            },
        })

        # Place and fill the SELL.
        b.apply({
            "event_id": "so1",
            "type": "order_placed",
            "payload": {
                "order_id": "SELL1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "5",
                "limit_price": "120.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        b.apply({
            "event_id": "sf1",
            "type": "order_filled",
            "payload": {
                "order_id": "SELL1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "5",
                "price": "120.00",
                "principal": "600.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "SELL-T1",
            },
        })

        self.assertEqual(
            b.trades["SELL-T1"]["side"],
            "sell",
        )

        self.assertEqual(
            b.trades["SELL-T1"]["principal"],
            D("600.00"),
        )

        legs = b.apply({
            "event_id": "ss1",
            "type": "trade_settled",
            "payload": {
                "trade_id": "SELL-T1",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "600.00",
                    "credit": "0.00",
                },
                {
                    "account": "1150",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "600.00",
                },
            ],
        )

        self.assertTrue(
            b.trades["SELL-T1"]["settled"]
        )

        self.assertEqual(
            b.snapshot()["trial_balance"]["1150"],
            "0.00",
        )

    def test_partial_fill_trades_settle_independently(self):
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

        # First trade: 4 shares / $400.
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

        # Second trade: remaining 6 shares / $600.
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

        self.assertEqual(
            b.trades["T1"]["principal"],
            D("400.00"),
        )

        self.assertEqual(
            b.trades["T2"]["principal"],
            D("600.00"),
        )

        self.assertFalse(b.trades["T1"]["settled"])
        self.assertFalse(b.trades["T2"]["settled"])

        # Settle only T1.
        legs = b.apply({
            "event_id": "st1",
            "type": "trade_settled",
            "payload": {
                "trade_id": "T1",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "2350",
                    "customer_id": "C1",
                    "debit": "400.00",
                    "credit": "0.00",
                },
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "400.00",
                },
            ],
        )

        self.assertTrue(b.trades["T1"]["settled"])
        self.assertFalse(b.trades["T2"]["settled"])

        # $600 of the original $1000 payable must remain.
        self.assertEqual(
            b.snapshot()["trial_balance"]["2350"],
            "-600.00",
        )

        # Now settle T2.
        b.apply({
            "event_id": "st2",
            "type": "trade_settled",
            "payload": {
                "trade_id": "T2",
            },
        })

        self.assertTrue(b.trades["T2"]["settled"])

        # Both trades are now settled.
        self.assertEqual(
            b.snapshot()["trial_balance"]["2350"],
            "0.00",
        )

class TestPayableSettlements(unittest.TestCase):

    def _create_buy_trade(
        self,
        b,
        suffix,
        customer_id="C1",
        broker="BRK-A",
        principal="1000.00",
    ):
        b.apply({
            "event_id": f"o-{suffix}",
            "type": "order_placed",
            "payload": {
                "order_id": f"ORD-{suffix}",
                "customer_id": customer_id,
                "side": "buy",
                "symbol": "ACME",
                "quantity": "10",
                "limit_price": "100.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        return b.apply({
            "event_id": f"f-{suffix}",
            "type": "order_filled",
            "payload": {
                "order_id": f"ORD-{suffix}",
                "customer_id": customer_id,
                "side": "buy",
                "symbol": "ACME",
                "quantity": "10",
                "price": "100.00",
                "principal": principal,
                "asset_class": "equity",
                "broker": broker,
                "partner_rate": "0.50",
                "trade_id": f"T-{suffix}",
            },
        })


    def test_broker_fee_settlement_clears_brk_a_payable(self):
        b = Book()
        self._create_buy_trade(b, "A", broker="BRK-A")

        self.assertEqual(
            b.snapshot()["trial_balance"]["2411"],
            "-1.25",
        )

        legs = b.apply({
            "event_id": "bs-A",
            "type": "broker_fees_settled",
            "payload": {
                "customer_id": "C1",
                "broker": "BRK-A",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "2411",
                    "customer_id": "C1",
                    "debit": "1.25",
                    "credit": "0.00",
                },
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "1.25",
                },
            ],
        )

        self.assertEqual(
            b.snapshot()["trial_balance"]["2411"],
            "0.00",
        )


    def test_broker_routes_to_correct_payable_accounts(self):
        cases = [
            ("BRK-A", "2411", "1.25"),
            ("BRK-B", "2412", "3.80"),
            ("BRK-C", "2413", "1.40"),
        ]

        for index, (broker, account, amount) in enumerate(cases):
            b = Book()

            self._create_buy_trade(
                b,
                str(index),
                broker=broker,
            )

            self.assertEqual(
                b.snapshot()["trial_balance"][account],
                f"-{amount}",
            )

            legs = b.apply({
                "event_id": f"bs-{index}",
                "type": "broker_fees_settled",
                "payload": {
                    "customer_id": "C1",
                    "broker": broker,
                },
            })

            self.assertEqual(
                legs[0]["account"],
                account,
            )

            self.assertEqual(
                legs[0]["debit"],
                amount,
            )

            self.assertEqual(
                b.snapshot()["trial_balance"][account],
                "0.00",
            )


    def test_custodian_fee_settlement_clears_full_payable(self):
        b = Book()
        self._create_buy_trade(b, "CUST")

        self.assertEqual(
            b.snapshot()["trial_balance"]["2420"],
            "-0.20",
        )

        legs = b.apply({
            "event_id": "cust-settle",
            "type": "custodian_fees_settled",
            "payload": {
                "customer_id": "C1",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "2420",
                    "customer_id": "C1",
                    "debit": "0.20",
                    "credit": "0.00",
                },
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "0.20",
                },
            ],
        )

        self.assertEqual(
            b.snapshot()["trial_balance"]["2420"],
            "0.00",
        )


    def test_reg_fee_remittance_clears_full_payable(self):
        b = Book()
        self._create_buy_trade(b, "REG")

        self.assertEqual(
            b.snapshot()["trial_balance"]["2400"],
            "-0.80",
        )

        legs = b.apply({
            "event_id": "reg-settle",
            "type": "reg_fees_remitted",
            "payload": {
                "customer_id": "C1",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "2400",
                    "customer_id": "C1",
                    "debit": "0.80",
                    "credit": "0.00",
                },
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "0.80",
                },
            ],
        )

        self.assertEqual(
            b.snapshot()["trial_balance"]["2400"],
            "0.00",
        )


    def test_partner_payout_clears_full_payable(self):
        b = Book()
        self._create_buy_trade(b, "PARTNER")

        self.assertEqual(
            b.snapshot()["trial_balance"]["2430"],
            "-0.48",
        )

        legs = b.apply({
            "event_id": "partner-settle",
            "type": "partner_payout",
            "payload": {
                "customer_id": "C1",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "2430",
                    "customer_id": "C1",
                    "debit": "0.48",
                    "credit": "0.00",
                },
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "0.48",
                },
            ],
        )

        self.assertEqual(
            b.snapshot()["trial_balance"]["2430"],
            "0.00",
        )


    def test_second_settlement_with_nothing_outstanding_is_rejected(self):
        b = Book()
        self._create_buy_trade(b, "DUP")

        first = b.apply({
            "event_id": "bs-1",
            "type": "broker_fees_settled",
            "payload": {
                "customer_id": "C1",
                "broker": "BRK-A",
            },
        })

        self.assertTrue(first)

        before = b.snapshot()

        second = b.apply({
            "event_id": "bs-2",
            "type": "broker_fees_settled",
            "payload": {
                "customer_id": "C1",
                "broker": "BRK-A",
            },
        })

        self.assertEqual(second, [])
        self.assertEqual(b.snapshot(), before)


    def test_settlement_is_per_customer(self):
        b = Book()

        self._create_buy_trade(
            b,
            "C1",
            customer_id="C1",
            broker="BRK-A",
        )

        self._create_buy_trade(
            b,
            "C2",
            customer_id="C2",
            broker="BRK-A",
        )

        self.assertEqual(
            b.balances[("C1", "2411")],
            D("-1.25"),
        )

        self.assertEqual(
            b.balances[("C2", "2411")],
            D("-1.25"),
        )

        b.apply({
            "event_id": "settle-C1",
            "type": "broker_fees_settled",
            "payload": {
                "customer_id": "C1",
                "broker": "BRK-A",
            },
        })

        self.assertEqual(
            b.balances[("C1", "2411")],
            D("0.00"),
        )

        self.assertEqual(
            b.balances[("C2", "2411")],
            D("-1.25"),
        )


    def test_multiple_trades_accumulate_before_single_settlement(self):
        b = Book()

        self._create_buy_trade(b, "M1", broker="BRK-A")
        self._create_buy_trade(b, "M2", broker="BRK-A")

        self.assertEqual(
            b.balances[("C1", "2411")],
            D("-2.50"),
        )

        legs = b.apply({
            "event_id": "settle-all",
            "type": "broker_fees_settled",
            "payload": {
                "customer_id": "C1",
                "broker": "BRK-A",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "2411",
                    "customer_id": "C1",
                    "debit": "2.50",
                    "credit": "0.00",
                },
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "2.50",
                },
            ],
        )

        self.assertEqual(
            b.balances[("C1", "2411")],
            D("0.00"),
        )

class TestCorporateActions(unittest.TestCase):

    def test_cash_dividend_credits_wallet_with_net_amount(self):
        b = Book()

        legs = b.apply({
            "event_id": "div1",
            "type": "dividend_cash",
            "payload": {
                "customer_id": "C1",
                "symbol": "ACME",
                "gross_amount": "100.00",
                "withholding_tax": "15.00",
                "net_amount": "85.00",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "85.00",
                    "credit": "0.00",
                },
                {
                    "account": "2010",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "85.00",
                },
            ],
        )

        snap = b.snapshot()

        self.assertEqual(
            snap["customers"]["C1"]["wallet_cash"],
            "85.00",
        )

        self.assertEqual(
            snap["trial_balance"]["1100"],
            "85.00",
        )

        self.assertEqual(
            snap["trial_balance"]["2010"],
            "-85.00",
        )


    def test_invalid_cash_dividend_is_rejected_without_state_change(self):
        b = Book()

        before = b.snapshot()

        # 100 - 15 != 90
        legs = b.apply({
            "event_id": "div-invalid",
            "type": "dividend_cash",
            "payload": {
                "customer_id": "C1",
                "symbol": "ACME",
                "gross_amount": "100.00",
                "withholding_tax": "15.00",
                "net_amount": "90.00",
            },
        })

        self.assertEqual(legs, [])
        self.assertEqual(b.snapshot(), before)


    def test_reinvested_dividend_creates_position_without_cash(self):
        b = Book()

        legs = b.apply({
            "event_id": "dr1",
            "type": "dividend_reinvested",
            "payload": {
                "customer_id": "C1",
                "symbol": "ACME",
                "gross_amount": "100.00",
                "withholding_tax": "15.00",
                "net_amount": "85.00",
                "reinvest_price": "17.00",
                "reinvest_quantity": "5",
            },
        })

        self.assertEqual(
            legs,
            [
                {
                    "account": "1200",
                    "customer_id": "C1",
                    "debit": "85.00",
                    "credit": "0.00",
                },
                {
                    "account": "2100",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "85.00",
                },
            ],
        )

        snap = b.snapshot()

        self.assertEqual(
            snap["customers"]["C1"]["wallet_cash"],
            "0.00",
        )

        self.assertEqual(
            snap["customers"]["C1"]["positions"]["ACME"],
            {
                "quantity": "5.00",
                "cost_basis": "85.00",
            },
        )


    def test_reinvested_dividend_appends_fifo_lot(self):
        b = Book()

        b.lots[("C1", "ACME")] = [
            {
                "event_id": "old",
                "trade_id": "T1",
                "quantity": D("10"),
                "cost": D("1000.00"),
            }
        ]

        b.apply({
            "event_id": "dr2",
            "type": "dividend_reinvested",
            "payload": {
                "customer_id": "C1",
                "symbol": "ACME",
                "gross_amount": "100.00",
                "withholding_tax": "15.00",
                "net_amount": "85.00",
                "reinvest_price": "17.00",
                "reinvest_quantity": "5",
            },
        })

        lots = b.lots[("C1", "ACME")]

        self.assertEqual(len(lots), 2)

        self.assertEqual(
            lots[0]["trade_id"],
            "T1",
        )

        self.assertEqual(
            lots[0]["quantity"],
            D("10"),
        )

        self.assertEqual(
            lots[1]["event_id"],
            "dr2",
        )

        self.assertEqual(
            lots[1]["quantity"],
            D("5"),
        )

        self.assertEqual(
            lots[1]["cost"],
            D("85.00"),
        )


    def test_stock_split_scales_each_lot_and_preserves_cost(self):
        b = Book()

        b.lots[("C1", "ACME")] = [
            {
                "event_id": "x1",
                "trade_id": "T1",
                "quantity": D("10"),
                "cost": D("1000.00"),
            },
            {
                "event_id": "x2",
                "trade_id": "T2",
                "quantity": D("5"),
                "cost": D("600.00"),
            },
        ]

        legs = b.apply({
            "event_id": "split1",
            "type": "stock_split",
            "payload": {
                "customer_id": "C1",
                "symbol": "ACME",
                "ratio_from": "1",
                "ratio_to": "2",
            },
        })

        self.assertEqual(legs, [])

        lots = b.lots[("C1", "ACME")]

        self.assertEqual(lots[0]["quantity"], D("20"))
        self.assertEqual(lots[0]["cost"], D("1000.00"))

        self.assertEqual(lots[1]["quantity"], D("10"))
        self.assertEqual(lots[1]["cost"], D("600.00"))

        position = (
            b.snapshot()["customers"]["C1"]["positions"]["ACME"]
        )

        self.assertEqual(
            position,
            {
                "quantity": "30.00",
                "cost_basis": "1600.00",
            },
        )


    def test_stock_split_is_customer_specific(self):
        b = Book()

        b.lots[("C1", "ACME")] = [{
            "event_id": "c1",
            "trade_id": "T1",
            "quantity": D("10"),
            "cost": D("1000.00"),
        }]

        b.lots[("C2", "ACME")] = [{
            "event_id": "c2",
            "trade_id": "T2",
            "quantity": D("7"),
            "cost": D("700.00"),
        }]

        b.apply({
            "event_id": "split-C1",
            "type": "stock_split",
            "payload": {
                "customer_id": "C1",
                "symbol": "ACME",
                "ratio_from": "1",
                "ratio_to": "2",
            },
        })

        self.assertEqual(
            b.lots[("C1", "ACME")][0]["quantity"],
            D("20"),
        )

        # C2 must be completely untouched.
        self.assertEqual(
            b.lots[("C2", "ACME")][0]["quantity"],
            D("7"),
        )

        self.assertEqual(
            b.lots[("C2", "ACME")][0]["cost"],
            D("700.00"),
        )


    def test_symbol_change_rekeys_lots_without_changing_position(self):
        b = Book()

        b.lots[("C1", "OLD")] = [
            {
                "event_id": "x1",
                "trade_id": "T1",
                "quantity": D("10"),
                "cost": D("1000.00"),
            },
            {
                "event_id": "x2",
                "trade_id": "T2",
                "quantity": D("5"),
                "cost": D("600.00"),
            },
        ]

        legs = b.apply({
            "event_id": "symbol1",
            "type": "symbol_change",
            "payload": {
                "customer_id": "C1",
                "old_symbol": "OLD",
                "new_symbol": "NEW",
            },
        })

        self.assertEqual(legs, [])

        self.assertNotIn(
            ("C1", "OLD"),
            b.lots,
        )

        self.assertIn(
            ("C1", "NEW"),
            b.lots,
        )

        snap = b.snapshot()

        self.assertNotIn(
            "OLD",
            snap["customers"]["C1"]["positions"],
        )

        self.assertEqual(
            snap["customers"]["C1"]["positions"]["NEW"],
            {
                "quantity": "15.00",
                "cost_basis": "1600.00",
            },
        )


    def test_symbol_change_does_not_affect_other_customer(self):
        b = Book()

        b.lots[("C1", "OLD")] = [{
            "event_id": "x1",
            "trade_id": "T1",
            "quantity": D("10"),
            "cost": D("1000.00"),
        }]

        b.lots[("C2", "OLD")] = [{
            "event_id": "x2",
            "trade_id": "T2",
            "quantity": D("8"),
            "cost": D("800.00"),
        }]

        b.apply({
            "event_id": "symbol-C1",
            "type": "symbol_change",
            "payload": {
                "customer_id": "C1",
                "old_symbol": "OLD",
                "new_symbol": "NEW",
            },
        })

        self.assertIn(
            ("C1", "NEW"),
            b.lots,
        )

        self.assertNotIn(
            ("C1", "OLD"),
            b.lots,
        )

        # C2 still owns OLD.
        self.assertIn(
            ("C2", "OLD"),
            b.lots,
        )

        self.assertEqual(
            b.lots[("C2", "OLD")][0]["quantity"],
            D("8"),
        )

        self.assertEqual(
            b.lots[("C2", "OLD")][0]["cost"],
            D("800.00"),
        )

class TestReversals(unittest.TestCase):

    def test_deposit_reversal_exactly_inverts_journal(self):
        b = Book()

        original = b.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "100.00",
            },
        })

        reversal = b.apply({
            "event_id": "rev-1",
            "type": "reversal",
            "payload": {
                "reverses_event_id": "dep-1",
                "reason": "mistake",
            },
        })

        self.assertEqual(len(original), len(reversal))

        for orig, rev in zip(original, reversal):
            self.assertEqual(orig["account"], rev["account"])
            self.assertEqual(
                orig["customer_id"],
                rev["customer_id"],
            )
            self.assertEqual(orig["debit"], rev["credit"])
            self.assertEqual(orig["credit"], rev["debit"])

        snap = b.snapshot()

        self.assertEqual(
            snap["customers"]["C1"]["wallet_cash"],
            "0.00",
        )
        self.assertEqual(
            snap["trial_balance"]["1100"],
            "0.00",
        )
        self.assertEqual(
            snap["trial_balance"]["2010"],
            "0.00",
        )

    def test_unknown_reversal_is_rejected_without_state_change(self):
        b = Book()

        b.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "100.00",
            },
        })

        before = b.snapshot()

        result = b.apply({
            "event_id": "rev-1",
            "type": "reversal",
            "payload": {
                "reverses_event_id": "does-not-exist",
                "reason": "mistake",
            },
        })

        self.assertEqual(result, [])
        self.assertEqual(b.snapshot(), before)
        self.assertNotIn("rev-1", b.events)

    def test_same_event_cannot_be_reversed_twice(self):
        b = Book()

        b.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "100.00",
            },
        })

        b.apply({
            "event_id": "rev-1",
            "type": "reversal",
            "payload": {
                "reverses_event_id": "dep-1",
                "reason": "first reversal",
            },
        })

        before = b.snapshot()

        result = b.apply({
            "event_id": "rev-2",
            "type": "reversal",
            "payload": {
                "reverses_event_id": "dep-1",
                "reason": "second reversal",
            },
        })

        self.assertEqual(result, [])
        self.assertEqual(b.snapshot(), before)
        self.assertNotIn("rev-2", b.events)

    def test_duplicate_reversal_event_id_is_idempotent(self):
        b = Book()

        b.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "100.00",
            },
        })

        event = {
            "event_id": "rev-1",
            "type": "reversal",
            "payload": {
                "reverses_event_id": "dep-1",
                "reason": "mistake",
            },
        }

        first = b.apply(event)
        before = b.snapshot()

        second = b.apply(event)

        self.assertTrue(first)
        self.assertEqual(second, [])
        self.assertEqual(b.snapshot(), before)

    def test_buy_fill_reversal_removes_fifo_lot_without_restoring_hold(self):
        b = Book()

        b.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "2000.00",
            },
        })

        b.apply({
            "event_id": "ord-1",
            "type": "order_placed",
            "payload": {
                "order_id": "BUY-1",
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
            "event_id": "fill-1",
            "type": "order_filled",
            "payload": {
                "order_id": "BUY-1",
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

        b.apply({
            "event_id": "rev-1",
            "type": "reversal",
            "payload": {
                "reverses_event_id": "fill-1",
                "reason": "bad fill",
            },
        })

        snap = b.snapshot()

        self.assertNotIn(
            "ACME",
            snap["customers"]["C1"]["positions"],
        )

        self.assertEqual(
            snap["customers"]["C1"]["cash_hold"],
            "0.00",
        )

        self.assertEqual(
            b.orders["BUY-1"]["status"],
            "filled",
        )
        self.assertEqual(
            b.orders["BUY-1"]["remaining_quantity"],
            D("0.00"),
        )
        self.assertEqual(
            b.orders["BUY-1"]["remaining_cash_hold"],
            D("0.00"),
        )

    def test_sell_fill_reversal_restores_exact_fifo_lots(self):
        b = Book()

        b.lots[("C1", "ACME")] = [
            {
                "event_id": "buy-1",
                "trade_id": "T1",
                "quantity": D("10"),
                "cost": D("1000.00"),
            },
            {
                "event_id": "buy-2",
                "trade_id": "T2",
                "quantity": D("5"),
                "cost": D("600.00"),
            },
        ]

        b.apply({
            "event_id": "ord-1",
            "type": "order_placed",
            "payload": {
                "order_id": "SELL-1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "12",
                "limit_price": "120.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        b.apply({
            "event_id": "sell-1",
            "type": "order_filled",
            "payload": {
                "order_id": "SELL-1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "12",
                "price": "120.00",
                "principal": "1440.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "ST1",
            },
        })

        b.apply({
            "event_id": "rev-1",
            "type": "reversal",
            "payload": {
                "reverses_event_id": "sell-1",
                "reason": "bad sell",
            },
        })

        lots = b.lots[("C1", "ACME")]

        self.assertEqual(len(lots), 2)

        self.assertEqual(lots[0]["event_id"], "buy-1")
        self.assertEqual(lots[0]["trade_id"], "T1")
        self.assertEqual(lots[0]["quantity"], D("10"))
        self.assertEqual(lots[0]["cost"], D("1000.00"))

        self.assertEqual(lots[1]["event_id"], "buy-2")
        self.assertEqual(lots[1]["trade_id"], "T2")
        self.assertEqual(lots[1]["quantity"], D("5"))
        self.assertEqual(lots[1]["cost"], D("600.00"))

        position = b.snapshot()["customers"]["C1"]["positions"]["ACME"]

        self.assertEqual(position["quantity"], "15.00")
        self.assertEqual(position["cost_basis"], "1600.00")

        self.assertEqual(
            b.orders["SELL-1"]["status"],
            "filled",
        )

class TestResilience(unittest.TestCase):

    def test_rejected_event_id_remains_seen(self):
        b = Book()

        bad = {
            "event_id": "bad-fx-1",
            "type": "fx_deposit",
            "payload": {
                "customer_id": "C1",
                "amount_foreign": "100.00",
                "currency": "EUR",
                "market_rate": "1.10",
                "customer_rate": "1.20",
                "usd_at_market_rate": "110.00",
                "usd_at_customer_rate": "120.00",
            },
        }

        result = b.apply(bad)

        self.assertEqual(result, [])
        self.assertIn("bad-fx-1", b.seen)
        self.assertNotIn("bad-fx-1", b.events)

    def test_redelivery_of_rejected_event_stays_rejected(self):
        b = Book()

        bad = {
            "event_id": "bad-fx-1",
            "type": "fx_deposit",
            "payload": {
                "customer_id": "C1",
                "amount_foreign": "100.00",
                "currency": "EUR",
                "market_rate": "1.10",
                "customer_rate": "1.20",
                "usd_at_market_rate": "110.00",
                "usd_at_customer_rate": "120.00",
            },
        }

        self.assertEqual(b.apply(bad), [])
        before = b.snapshot()

        # Same event_id, but now with content that would otherwise be valid.
        conflicting_redelivery = {
            "event_id": "bad-fx-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "9999.00",
            },
        }

        result = b.apply(conflicting_redelivery)

        self.assertEqual(result, [])
        self.assertEqual(b.snapshot(), before)
        self.assertNotIn("bad-fx-1", b.events)

    def test_conflicting_duplicate_of_posted_event_first_delivery_wins(self):
        b = Book()

        first = {
            "event_id": "dup-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "100.00",
            },
        }

        conflicting = {
            "event_id": "dup-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "9999.00",
            },
        }

        first_legs = b.apply(first)
        before = b.snapshot()

        second_legs = b.apply(conflicting)

        self.assertTrue(first_legs)
        self.assertEqual(second_legs, [])
        self.assertEqual(b.snapshot(), before)

        self.assertEqual(
            b.snapshot()["customers"]["C1"]["wallet_cash"],
            "100.00",
        )

        # The accepted audit event must remain the FIRST delivery.
        self.assertEqual(
            b.events["dup-1"]["payload"]["amount"],
            "100.00",
        )

    def test_oversell_fill_is_atomic_and_does_not_consume_fifo(self):
        b = Book()

        b.lots[("C1", "ACME")] = [
            {
                "event_id": "buy-1",
                "trade_id": "T1",
                "quantity": D("10"),
                "cost": D("1000.00"),
            },
        ]

        before_lots = [
            dict(lot) for lot in b.lots[("C1", "ACME")]
        ]
        before = b.snapshot()

        result = b.apply({
            "event_id": "sell-bad-1",
            "type": "order_filled",
            "payload": {
                "order_id": "MISSING-ORDER",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "12",
                "price": "120.00",
                "principal": "1440.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "ST-BAD",
            },
        })

        self.assertEqual(result, [])
        self.assertEqual(b.snapshot(), before)

        self.assertEqual(
            b.lots[("C1", "ACME")],
            before_lots,
        )

        self.assertIn("sell-bad-1", b.seen)
        self.assertNotIn("sell-bad-1", b.events)

    def test_oversell_order_rejection_leaves_state_unchanged(self):
        b = Book()

        b.lots[("C1", "ACME")] = [
            {
                "event_id": "buy-1",
                "trade_id": "T1",
                "quantity": D("10"),
                "cost": D("1000.00"),
            },
        ]

        before = b.snapshot()
        before_lots = [
            dict(lot) for lot in b.lots[("C1", "ACME")]
        ]

        result = b.apply({
            "event_id": "oversell-1",
            "type": "order_placed",
            "payload": {
                "order_id": "SELL-1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "11",
                "limit_price": "120.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        self.assertEqual(result, [])
        self.assertEqual(b.snapshot(), before)

        self.assertEqual(
            b.lots[("C1", "ACME")],
            before_lots,
        )

        self.assertNotIn("SELL-1", b.orders)

        # Rejected IDs are still seen.
        self.assertIn("oversell-1", b.seen)

    def test_invalid_partial_fill_does_not_mutate_buy_order(self):
        b = Book()

        b.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "2000.00",
            },
        })

        b.apply({
            "event_id": "ord-1",
            "type": "order_placed",
            "payload": {
                "order_id": "BUY-1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "10",
                "limit_price": "100.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        before_snapshot = b.snapshot()
        before_order = dict(b.orders["BUY-1"])
        before_lots = [
            dict(x) for x in b.lots.get(("C1", "ACME"), [])
        ]

        # Fill exceeds the order's remaining quantity.
        result = b.apply({
            "event_id": "bad-fill-1",
            "type": "order_partially_filled",
            "payload": {
                "order_id": "BUY-1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "11",
                "price": "100.00",
                "principal": "1100.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "BAD-T1",
            },
        })

        self.assertEqual(result, [])
        self.assertEqual(b.snapshot(), before_snapshot)
        self.assertEqual(b.orders["BUY-1"], before_order)
        self.assertEqual(
            b.lots.get(("C1", "ACME"), []),
            before_lots,
        )
        self.assertNotIn("BAD-T1", b.trades)

        # Rejected delivery is nevertheless seen.
        self.assertIn("bad-fill-1", b.seen)

    def test_invalid_partial_fill_does_not_mutate_sell_order_or_fifo(self):
        b = Book()

        b.lots[("C1", "ACME")] = [
            {
                "event_id": "buy-1",
                "trade_id": "T1",
                "quantity": D("10"),
                "cost": D("1000.00"),
            },
        ]

        b.apply({
            "event_id": "ord-1",
            "type": "order_placed",
            "payload": {
                "order_id": "SELL-1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "8",
                "limit_price": "120.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        before_snapshot = b.snapshot()
        before_order = dict(b.orders["SELL-1"])
        before_lots = [
            dict(x) for x in b.lots[("C1", "ACME")]
        ]

        # Order only has 8 shares remaining, so 9 must reject.
        result = b.apply({
            "event_id": "bad-fill-1",
            "type": "order_partially_filled",
            "payload": {
                "order_id": "SELL-1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "9",
                "price": "120.00",
                "principal": "1080.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "BAD-T1",
            },
        })

        self.assertEqual(result, [])
        self.assertEqual(b.snapshot(), before_snapshot)
        self.assertEqual(b.orders["SELL-1"], before_order)
        self.assertEqual(
            b.lots[("C1", "ACME")],
            before_lots,
        )
        self.assertNotIn("BAD-T1", b.trades)
        self.assertIn("bad-fill-1", b.seen)

    def test_duplicate_trade_id_fill_rejection_is_atomic(self):
        b = Book()

        b.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "5000.00",
            },
        })

        # First BUY order.
        b.apply({
            "event_id": "ord-1",
            "type": "order_placed",
            "payload": {
                "order_id": "BUY-1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "5",
                "limit_price": "100.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        # This creates trade_id T-DUP.
        first_fill = b.apply({
            "event_id": "fill-1",
            "type": "order_filled",
            "payload": {
                "order_id": "BUY-1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "5",
                "price": "100.00",
                "principal": "500.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T-DUP",
            },
        })

        self.assertTrue(first_fill)
        self.assertIn("T-DUP", b.trades)

        # Second independent BUY order.
        b.apply({
            "event_id": "ord-2",
            "type": "order_placed",
            "payload": {
                "order_id": "BUY-2",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "3",
                "limit_price": "100.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        before_snapshot = b.snapshot()
        before_order = dict(b.orders["BUY-2"])
        before_lots = [
            dict(x) for x in b.lots[("C1", "ACME")]
        ]
        before_trades = {
            key: dict(value)
            for key, value in b.trades.items()
        }

        # Different event, but duplicate trade_id.
        result = b.apply({
            "event_id": "fill-2",
            "type": "order_filled",
            "payload": {
                "order_id": "BUY-2",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "3",
                "price": "100.00",
                "principal": "300.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T-DUP",
            },
        })

        self.assertEqual(result, [])

        # Rejection must leave absolutely everything unchanged.
        self.assertEqual(b.snapshot(), before_snapshot)
        self.assertEqual(
            b.orders["BUY-2"],
            before_order,
        )
        self.assertEqual(
            b.lots[("C1", "ACME")],
            before_lots,
        )
        self.assertEqual(
            b.trades,
            before_trades,
        )

        self.assertIn("fill-2", b.seen)
        self.assertNotIn("fill-2", b.events)

    def test_duplicate_trade_id_sell_fill_rejection_is_atomic(self):
        b = Book()

        # Give C1 a position of 10 ACME shares.
        b.lots[("C1", "ACME")] = [
            {
                "event_id": "buy-1",
                "trade_id": "ORIGINAL-BUY",
                "quantity": D("10"),
                "cost": D("1000.00"),
            },
        ]

        # Create a valid trade_id using an independent BUY.
        b.apply({
            "event_id": "dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C2",
                "amount": "2000.00",
            },
        })

        b.apply({
            "event_id": "buy-order-1",
            "type": "order_placed",
            "payload": {
                "order_id": "BUY-C2",
                "customer_id": "C2",
                "side": "buy",
                "symbol": "XYZ",
                "quantity": "1",
                "limit_price": "100.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        first_fill = b.apply({
            "event_id": "buy-fill-1",
            "type": "order_filled",
            "payload": {
                "order_id": "BUY-C2",
                "customer_id": "C2",
                "side": "buy",
                "symbol": "XYZ",
                "quantity": "1",
                "price": "100.00",
                "principal": "100.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T-DUP-SELL",
            },
        })

        self.assertTrue(first_fill)
        self.assertIn("T-DUP-SELL", b.trades)

        # C1 now places a legitimate SELL order.
        b.apply({
            "event_id": "sell-order-1",
            "type": "order_placed",
            "payload": {
                "order_id": "SELL-C1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "6",
                "limit_price": "120.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        before_snapshot = b.snapshot()
        before_order = dict(b.orders["SELL-C1"])
        before_lots = [
            dict(x) for x in b.lots[("C1", "ACME")]
        ]
        before_trades = {
            key: dict(value)
            for key, value in b.trades.items()
        }

        # The fill itself is otherwise valid, but deliberately reuses
        # an existing trade_id.
        result = b.apply({
            "event_id": "sell-fill-bad",
            "type": "order_filled",
            "payload": {
                "order_id": "SELL-C1",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "6",
                "price": "120.00",
                "principal": "720.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "T-DUP-SELL",
            },
        })

        self.assertEqual(result, [])

        # Nothing about C1's order or FIFO position may have changed.
        self.assertEqual(b.snapshot(), before_snapshot)
        self.assertEqual(
            b.orders["SELL-C1"],
            before_order,
        )
        self.assertEqual(
            b.lots[("C1", "ACME")],
            before_lots,
        )

        # Existing trade registry must also be untouched.
        self.assertEqual(
            b.trades,
            before_trades,
        )

        # First delivery of the rejected event is still considered seen.
        self.assertIn("sell-fill-bad", b.seen)
        self.assertNotIn("sell-fill-bad", b.events)

    def test_customer_positions_and_sell_holds_are_isolated(self):
        b = Book()

        # Both customers own the same symbol, but different quantities/costs.
        b.lots[("C1", "ACME")] = [
            {
                "event_id": "c1-buy",
                "trade_id": "C1-T1",
                "quantity": D("10"),
                "cost": D("1000.00"),
            },
        ]

        b.lots[("C2", "ACME")] = [
            {
                "event_id": "c2-buy",
                "trade_id": "C2-T1",
                "quantity": D("20"),
                "cost": D("3000.00"),
            },
        ]

        # C1 reserves 6 of its 10 shares.
        result = b.apply({
            "event_id": "c1-sell-order",
            "type": "order_placed",
            "payload": {
                "order_id": "C1-SELL",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "6",
                "limit_price": "120.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        self.assertEqual(result, [])

        # C1's hold must not affect C2.
        self.assertEqual(
            b._owned_quantity("C1", "ACME"),
            D("10"),
        )
        self.assertEqual(
            b._owned_quantity("C2", "ACME"),
            D("20"),
        )

        self.assertEqual(
            b._share_hold("C1", "ACME"),
            D("6"),
        )
        self.assertEqual(
            b._share_hold("C2", "ACME"),
            D("0"),
        )

        # C1 only has 4 unreserved shares, so another order for 5 rejects.
        rejected = b.apply({
            "event_id": "c1-oversell",
            "type": "order_placed",
            "payload": {
                "order_id": "C1-SELL-2",
                "customer_id": "C1",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "5",
                "limit_price": "120.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        self.assertEqual(rejected, [])
        self.assertNotIn("C1-SELL-2", b.orders)

        # C2 still independently has all 20 shares available.
        accepted = b.apply({
            "event_id": "c2-sell-order",
            "type": "order_placed",
            "payload": {
                "order_id": "C2-SELL",
                "customer_id": "C2",
                "side": "sell",
                "symbol": "ACME",
                "quantity": "20",
                "limit_price": "120.00",
                "asset_class": "equity",
                "est_charges": "10.00",
            },
        })

        self.assertEqual(accepted, [])
        self.assertIn("C2-SELL", b.orders)

        snap = b.snapshot()

        self.assertEqual(
            snap["customers"]["C1"]["positions"]["ACME"],
            {
                "quantity": "10.00",
                "cost_basis": "1000.00",
            },
        )

        self.assertEqual(
            snap["customers"]["C2"]["positions"]["ACME"],
            {
                "quantity": "20.00",
                "cost_basis": "3000.00",
            },
        )

    def test_replay_of_processed_lifecycle_does_not_change_state(self):
        b = Book()

        events = [
            {
                "event_id": "replay-dep",
                "type": "deposit",
                "payload": {
                    "customer_id": "C1",
                    "amount": "5000.00",
                },
            },
            {
                "event_id": "replay-order",
                "type": "order_placed",
                "payload": {
                    "order_id": "REPLAY-BUY",
                    "customer_id": "C1",
                    "side": "buy",
                    "symbol": "ACME",
                    "quantity": "10",
                    "limit_price": "100.00",
                    "asset_class": "equity",
                    "est_charges": "10.00",
                },
            },
            {
                "event_id": "replay-fill",
                "type": "order_filled",
                "payload": {
                    "order_id": "REPLAY-BUY",
                    "customer_id": "C1",
                    "side": "buy",
                    "symbol": "ACME",
                    "quantity": "10",
                    "price": "100.00",
                    "principal": "1000.00",
                    "asset_class": "equity",
                    "broker": "BRK-A",
                    "partner_rate": "0.50",
                    "trade_id": "REPLAY-T1",
                },
            },
            {
                "event_id": "replay-settle",
                "type": "trade_settled",
                "payload": {
                    "trade_id": "REPLAY-T1",
                },
            },
        ]

        # First delivery.
        for event in events:
            b.apply(event)

        before_snapshot = b.snapshot()
        before_orders = {
            key: dict(value)
            for key, value in b.orders.items()
        }
        before_trades = {
            key: dict(value)
            for key, value in b.trades.items()
        }
        before_lots = {
            key: [dict(lot) for lot in lots]
            for key, lots in b.lots.items()
        }

        # Simulate the server replaying the same processed range.
        replay_results = [
            b.apply(event)
            for event in events
        ]

        # Every duplicate should produce no new journal.
        self.assertEqual(
            replay_results,
            [[], [], [], []],
        )

        # Absolutely no economic/internal state should change.
        self.assertEqual(
            b.snapshot(),
            before_snapshot,
        )
        self.assertEqual(
            b.orders,
            before_orders,
        )
        self.assertEqual(
            b.trades,
            before_trades,
        )
        self.assertEqual(
            dict(b.lots),
            before_lots,
        )

        # The original accepted audit records remain present.
        for event in events:
            self.assertIn(event["event_id"], b.events)

class TestCheckpointState(unittest.TestCase):

    def test_trial_balance_aggregates_across_customers(self):
        b = Book()

        b.apply({
            "event_id": "cp-dep-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "100.00",
            },
        })

        b.apply({
            "event_id": "cp-dep-2",
            "type": "deposit",
            "payload": {
                "customer_id": "C2",
                "amount": "250.00",
            },
        })

        snap = b.snapshot()

        self.assertEqual(snap["trial_balance"]["1100"], "350.00")
        self.assertEqual(snap["trial_balance"]["2010"], "-350.00")
        self.assertEqual(
            snap["customers"]["C1"]["wallet_cash"],
            "100.00",
        )
        self.assertEqual(
            snap["customers"]["C2"]["wallet_cash"],
            "250.00",
        )

    def test_zero_balance_accounts_remain_in_trial_balance(self):
        b = Book()

        b.apply({
            "event_id": "cp-dep-zero",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "100.00",
            },
        })

        b.apply({
            "event_id": "cp-rev-zero",
            "type": "reversal",
            "payload": {
                "reverses_event_id": "cp-dep-zero",
                "reason": "checkpoint zero-balance test",
            },
        })

        snap = b.snapshot()

        self.assertIn("1100", snap["trial_balance"])
        self.assertIn("2010", snap["trial_balance"])
        self.assertEqual(snap["trial_balance"]["1100"], "0.00")
        self.assertEqual(snap["trial_balance"]["2010"], "0.00")

    def test_checkpoint_reports_wallet_hold_and_position(self):
        b = Book()

        b.apply({
            "event_id": "cp-deposit",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "3000.00",
            },
        })

        b.apply({
            "event_id": "cp-buy-order",
            "type": "order_placed",
            "payload": {
                "order_id": "CP-BUY-1",
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
            "event_id": "cp-buy-fill",
            "type": "order_filled",
            "payload": {
                "order_id": "CP-BUY-1",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "ACME",
                "quantity": "10",
                "price": "100.00",
                "principal": "1000.00",
                "asset_class": "equity",
                "broker": "BRK-A",
                "partner_rate": "0.50",
                "trade_id": "CP-T1",
            },
        })

        b.apply({
            "event_id": "cp-open-order",
            "type": "order_placed",
            "payload": {
                "order_id": "CP-BUY-2",
                "customer_id": "C1",
                "side": "buy",
                "symbol": "XYZ",
                "quantity": "5",
                "limit_price": "50.00",
                "asset_class": "equity",
                "est_charges": "5.00",
            },
        })

        snap = b.snapshot()
        customer = snap["customers"]["C1"]

        self.assertEqual(customer["wallet_cash"], "1996.80")
        self.assertEqual(customer["cash_hold"], "255.00")

        self.assertEqual(
            customer["positions"]["ACME"],
            {
                "quantity": "10.00",
                "cost_basis": "1000.00",
            },
        )

        self.assertNotIn("XYZ", customer["positions"])

    def test_snapshot_is_deterministic_and_does_not_mutate_book(self):
        b = Book()

        b.apply({
            "event_id": "cp-det-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C2",
                "amount": "200.00",
            },
        })

        b.apply({
            "event_id": "cp-det-2",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "100.00",
            },
        })

        balances_before = dict(b.balances)
        orders_before = {
            key: dict(value)
            for key, value in b.orders.items()
        }
        lots_before = {
            key: [dict(lot) for lot in value]
            for key, value in b.lots.items()
        }

        first = b.snapshot()
        second = b.snapshot()

        self.assertEqual(first, second)
        self.assertEqual(dict(b.balances), balances_before)
        self.assertEqual(b.orders, orders_before)

        lots_after = {
            key: [dict(lot) for lot in value]
            for key, value in b.lots.items()
        }
        self.assertEqual(lots_after, lots_before)

        self.assertEqual(
            list(first["customers"].keys()),
            ["C1", "C2"],
        )

if __name__ == "__main__":
    unittest.main()