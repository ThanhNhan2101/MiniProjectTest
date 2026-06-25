import uuid
from datetime import datetime, timezone

from django.test import SimpleTestCase

from core.order.services.event_processor import EventPayloadError, parse_order_event


class EventParserTests(SimpleTestCase):
    def test_parse_order_event_accepts_producer_payload(self):
        event = parse_order_event(
            {
                "event_id": "12345678-1234-5678-1234-567812345678",
                "run_id": "87654321-4321-8765-4321-876543218765",
                "order_id": "SHOPEE-12345678-00000001",
                "status": "created",
                "occurred_at": "2026-06-24T00:00:00+00:00",
            }
        )

        self.assertEqual(event.event_id, uuid.UUID("12345678-1234-5678-1234-567812345678"))
        self.assertEqual(event.status, "CREATED")
        self.assertEqual(event.occurred_at, datetime(2026, 6, 24, tzinfo=timezone.utc))

    def test_parse_order_event_rejects_unknown_status(self):
        with self.assertRaises(EventPayloadError):
            parse_order_event(
                {
                    "event_id": "12345678-1234-5678-1234-567812345678",
                    "run_id": "87654321-4321-8765-4321-876543218765",
                    "order_id": "SHOPEE-12345678-00000001",
                    "status": "CANCELLED",
                    "occurred_at": "2026-06-24T00:00:00+00:00",
                }
            )
