import socket

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from redis.exceptions import RedisError

from core.order.services.event_processor import EventPayloadError, process_order_event
from core.order.services.redis_stream import (
    acknowledge_events,
    ensure_consumer_group,
    get_redis_client,
    read_group,
)


class Command(BaseCommand):
    help = "Consume order events from Redis Streams and persist them to PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument("--stream", default=settings.REDIS_ORDER_STREAM)
        parser.add_argument("--group", default="order-workers")
        parser.add_argument("--consumer", default=socket.gethostname())
        parser.add_argument("--count", type=int, default=100)
        parser.add_argument("--block-ms", type=int, default=2000)
        parser.add_argument("--max-messages", type=int, default=0)

    def handle(self, *args, **options):
        stream_name = options["stream"].strip()
        group_name = options["group"].strip()
        consumer_name = options["consumer"].strip()
        batch_count = options["count"]
        block_ms = options["block_ms"]
        max_messages = options["max_messages"]

        if not stream_name:
            raise CommandError("--stream cannot be empty")
        if not group_name:
            raise CommandError("--group cannot be empty")
        if not consumer_name:
            raise CommandError("--consumer cannot be empty")
        if batch_count < 1:
            raise CommandError("--count must be at least 1")
        if block_ms < 1:
            raise CommandError("--block-ms must be at least 1")
        if max_messages < 0:
            raise CommandError("--max-messages cannot be negative")

        client = get_redis_client()
        processed = 0

        try:
            client.ping()
            ensure_consumer_group(client, stream_name, group_name)

            self.stdout.write(
                f"Consuming {stream_name} as {group_name}/{consumer_name}..."
            )

            while True:
                read_count = batch_count
                if max_messages:
                    remaining = max_messages - processed
                    if remaining <= 0:
                        break
                    read_count = min(batch_count, remaining)

                streams = read_group(
                    client=client,
                    stream_name=stream_name,
                    group_name=group_name,
                    consumer_name=consumer_name,
                    count=read_count,
                    block_ms=block_ms,
                )
                if not streams:
                    if max_messages:
                        break
                    continue

                ack_ids = []
                for _, entries in streams:
                    for stream_entry_id, payload in entries:
                        if max_messages and processed >= max_messages:
                            break

                        try:
                            result = process_order_event(
                                stream_entry_id=stream_entry_id,
                                payload=payload,
                            )
                        except (EventPayloadError, ObjectDoesNotExist, DatabaseError) as exc:
                            self.stderr.write(
                                f"Failed {stream_entry_id}; leaving pending for retry: {exc}"
                            )
                            continue

                        ack_ids.append(stream_entry_id)
                        processed += 1
                        self.stdout.write(
                            f"{stream_entry_id} {result.result} order={result.order_id}"
                        )

                    if max_messages and processed >= max_messages:
                        break

                acknowledged = acknowledge_events(
                    client=client,
                    stream_name=stream_name,
                    group_name=group_name,
                    stream_entry_ids=ack_ids,
                )
                if acknowledged:
                    self.stdout.write(f"ACK {acknowledged} event(s)")

                if max_messages and processed >= max_messages:
                    break
        except RedisError as exc:
            raise CommandError(f"Redis is unavailable: {exc}") from exc
        finally:
            client.close()

        self.stdout.write(self.style.SUCCESS(
            f"Processed {processed} event(s)."))
