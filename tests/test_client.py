import unittest

from client import ArenaClient


class FakeResponse:
    status_code = 200
    headers = {}

    def raise_for_status(self):
        pass


class FakeHTTP:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({
            "url": url,
            **kwargs,
        })
        return FakeResponse()


class TestCheckpointProtocol(unittest.TestCase):

    def test_checkpoint_captures_snapshot_before_flush(self):
        client = ArenaClient(
            url="https://example.test",
            key="test-key",
            mode="practice",
        )

        # State that exists at the checkpoint offset.
        client.book.apply({
            "event_id": "cp-deposit",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "100.00",
            },
        })

        # Normally handle() would have queued this posting.
        client.pending.append({
            "event_id": "cp-deposit",
            "legs": [
                {
                    "account": "1100",
                    "customer_id": "C1",
                    "debit": "100.00",
                    "credit": "0.00",
                },
                {
                    "account": "2010",
                    "customer_id": "C1",
                    "debit": "0.00",
                    "credit": "100.00",
                },
            ],
        })

        original_snapshot = client.book.snapshot()
        order = []

        # Instrument snapshot so we can observe when it happens.
        real_snapshot = client.book.snapshot

        def observed_snapshot():
            order.append("snapshot")
            return real_snapshot()

        client.book.snapshot = observed_snapshot

        http = FakeHTTP()

        # Instrument HTTP calls. The postings request must occur only
        # after snapshot() has already been captured.
        real_post = http.post

        def observed_post(url, **kwargs):
            if url.endswith("/v1/postings"):
                order.append("flush")
            elif url.endswith("/v1/checkpoint"):
                order.append("checkpoint")
            return real_post(url, **kwargs)

        http.post = observed_post

        client.checkpoint(http, "cp-test-1")

        self.assertEqual(
            order,
            ["snapshot", "flush", "checkpoint"],
        )

        self.assertEqual(len(http.calls), 2)

        postings_call = http.calls[0]
        checkpoint_call = http.calls[1]

        self.assertTrue(
            postings_call["url"].endswith("/v1/postings")
        )
        self.assertTrue(
            checkpoint_call["url"].endswith("/v1/checkpoint")
        )

        # Most important assertion:
        # the checkpoint payload is the state captured at the
        # checkpoint offset.
        self.assertEqual(
            checkpoint_call["json"],
            {
                "checkpoint_id": "cp-test-1",
                **original_snapshot,
            },
        )

        self.assertEqual(
            checkpoint_call["params"],
            {"mode": "practice"},
        )

        self.assertEqual(client.pending, [])
        self.assertEqual(client.stats["posted"], 1)
        self.assertEqual(client.stats["checkpoints"], 1)


if __name__ == "__main__":
    unittest.main()