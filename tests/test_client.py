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

    def test_replayed_event_is_idempotent(self):
        client = ArenaClient(
            url="https://example.test",
            key="test-key",
            mode="practice",
        )

        event = {
            "offset": 10,
            "event_id": "deposit-1",
            "type": "deposit",
            "payload": {
                "customer_id": "C1",
                "amount": "100.00",
            },
        }

        # First delivery.
        client.handle(event)

        after_first = client.book.snapshot()

        self.assertEqual(
            client.pending[-1]["legs"],
            [
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
        )

        # Simulate the server rewinding and redelivering exactly
        # the same event.
        client.handle(event)

        after_replay = client.book.snapshot()

        # Replay must not alter ledger state.
        self.assertEqual(after_replay, after_first)

        # But the replay still gets a submission.
        self.assertEqual(len(client.pending), 2)

        # Since this event_id was already processed, its replay
        # correctly produces no new legs.
        self.assertEqual(
            client.pending[1],
            {
                "event_id": "deposit-1",
                "legs": [],
            },
        )

        self.assertEqual(client.stats["events"], 2)

    def test_stream_reset_rewinds_cursor_flushes_and_returns(self):
            client = ArenaClient(
                url="https://example.test",
                key="test-key",
                mode="practice",
            )
    
            client.cursor = 10
    
            lines = [
                "event: ledger_event",
                'data: {"offset":10,"event_id":"reset-dep","type":"deposit","payload":{"customer_id":"C1","amount":"100.00"}}',
                "",
                "event: stream_reset",
                'data: {"resume_from":10}',
                "",
            ]
    
            http = FakeStreamHTTP(lines)
    
            client.consume(
                http,
                deadline=float("inf"),
            )
    
            # Event at offset 10 was processed first.
            self.assertEqual(
                client.book.snapshot()["customers"]["C1"]["wallet_cash"],
                "100.00",
            )
    
            # Processing offset 10 advanced us to 11, but reset explicitly
            # rewound the next connection back to 10.
            self.assertEqual(client.cursor, 10)
    
            self.assertEqual(client.stats["events"], 1)
            self.assertEqual(client.stats["resets"], 1)
    
            # Reset must flush the posting generated before the rewind.
            self.assertEqual(client.pending, [])
            self.assertEqual(client.stats["posted"], 1)
    
            self.assertEqual(len(http.stream_calls), 1)
    
            self.assertEqual(
                http.stream_calls[0]["params"],
                {
                    "mode": "practice",
                    "from": 10,
                },
            )
    
            self.assertEqual(len(http.calls), 1)
            self.assertTrue(
                http.calls[0]["url"].endswith("/v1/postings")
            )
    
            self.assertEqual(
                http.calls[0]["json"]["postings"][0]["event_id"],
                "reset-dep",
            )

    def test_stream_end_flushes_pending_and_marks_done(self):
        client = ArenaClient(
            url="https://example.test",
            key="test-key",
            mode="practice",
        )

        client.pending.append({
            "event_id": "end-event",
            "legs": [],
        })

        lines = [
            "event: stream_end",
            'data: {"reason":"completed"}',
            "",
        ]

        http = FakeStreamHTTP(lines)

        client.consume(
            http,
            deadline=float("inf"),
        )

        self.assertTrue(client.done)
        self.assertEqual(client.pending, [])
        self.assertEqual(client.stats["posted"], 1)

        self.assertEqual(len(http.calls), 1)
        self.assertTrue(
            http.calls[0]["url"].endswith("/v1/postings")
        )

        self.assertEqual(
            http.calls[0]["json"],
            {
                "postings": [
                    {
                        "event_id": "end-event",
                        "legs": [],
                    }
                ]
            },
        )

    def test_flush_sends_at_most_500_postings(self):
        client = ArenaClient(
            url="https://example.test",
            key="test-key",
            mode="practice",
        )

        client.pending = [
            {
                "event_id": f"batch-{i}",
                "legs": [],
            }
            for i in range(501)
        ]

        http = FakeHTTP()

        # First flush may send no more than 500.
        client.flush(http)

        self.assertEqual(len(http.calls), 1)
        self.assertEqual(
            len(http.calls[0]["json"]["postings"]),
            500,
        )

        self.assertEqual(client.stats["posted"], 500)

        # Exactly one posting must remain queued.
        self.assertEqual(len(client.pending), 1)
        self.assertEqual(
            client.pending[0]["event_id"],
            "batch-500",
        )

        # Second flush sends the remainder.
        client.flush(http)

        self.assertEqual(len(http.calls), 2)
        self.assertEqual(
            len(http.calls[1]["json"]["postings"]),
            1,
        )

        self.assertEqual(client.pending, [])
        self.assertEqual(client.stats["posted"], 501)

class FakeStreamResponse:
    def __init__(self, lines):
        self.lines = lines

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamHTTP(FakeHTTP):
    def __init__(self, lines):
        super().__init__()
        self.lines = lines
        self.stream_calls = []

    def stream(self, method, url, **kwargs):
        self.stream_calls.append({
            "method": method,
            "url": url,
            **kwargs,
        })
        return FakeStreamResponse(self.lines)

if __name__ == "__main__":
    unittest.main()