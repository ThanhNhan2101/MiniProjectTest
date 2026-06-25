import uuid
from datetime import datetime, timezone

from django.test import SimpleTestCase

from core.order.services.producer import (
    calculate_duplicate_count,
    generate_order_events,
)


class ProducerEventTests(SimpleTestCase):
    def test_calculate_duplicate_count(self):
        self.assertEqual(calculate_duplicate_count(100, 0.15), 15)

    def test_generate_exact_unique_and_duplicate_counts(self):
        events = list(
            generate_order_events(
                run_id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
                count=100,
                duplicate_count=15,
                source="shopee",
                seed=42,
                started_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
            )
        )

        self.assertEqual(len(events), 100)
        self.assertEqual(len({event["event_id"] for event in events}), 100)
        self.assertEqual(len({event["order_id"] for event in events}), 85)
        self.assertEqual(
            sum(event["is_duplicate"] == "1" for event in events),
            15,
        )
        self.assertTrue(all(event["run_id"] for event in events))

    def test_generation_is_reproducible_for_same_run_and_seed(self):
        arguments = {
            "run_id": uuid.UUID("12345678-1234-5678-1234-567812345678"),
            "count": 10,
            "duplicate_count": 2,
            "source": "shopee",
            "seed": 7,
            "started_at": datetime(2026, 6, 24, tzinfo=timezone.utc),
        }

        self.assertEqual(
            list(generate_order_events(**arguments)),
            list(generate_order_events(**arguments)),
        )

    def test_duplicate_rate_must_be_less_than_one(self):
        with self.assertRaises(ValueError):
            calculate_duplicate_count(100, 1)
