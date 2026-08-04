import unittest

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

        book.apply({
            "event_id": "i1",
            "type": "interest_credited",
            "payload": {
                "customer_id": "C1",
                "amount": "50.00",
            },
        })

        snapshot = book.snapshot()

        self.assertEqual(
            snapshot["customers"]["C1"]["wallet_cash"],
            "50.00",
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
                "foreign_amount": "100.00",
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
                "foreign_amount": "100.00",
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


if __name__ == "__main__":
    unittest.main()