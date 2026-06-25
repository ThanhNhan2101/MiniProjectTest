from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from redis.exceptions import RedisError

from core.order.models import LoadTestRun
from core.order.services.producer import (
    calculate_duplicate_count,
    generate_order_events,
)
from core.order.services.redis_stream import get_redis_client, publish_events


class Command(BaseCommand):
    help = "Generate order events and publish them to a Redis Stream."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=50_000)
        parser.add_argument("--duplicate-rate", type=float, default=0.15)
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--source", default="shopee")
        parser.add_argument("--stream", default=settings.REDIS_ORDER_STREAM)

    def handle(self, *args, **options):
        count = options["count"]
        duplicate_rate = options["duplicate_rate"]
        batch_size = options["batch_size"]
        source = options["source"].strip().lower()
        stream_name = options["stream"].strip()

        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1")
        if not source:
            raise CommandError("--source cannot be empty")
        if not stream_name:
            raise CommandError("--stream cannot be empty")

        try:
            duplicate_count = calculate_duplicate_count(count, duplicate_rate)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        unique_count = count - duplicate_count
        client = get_redis_client()

        try:
            client.ping()
        except RedisError as exc:
            raise CommandError(f"Redis is unavailable: {exc}") from exc

        run = LoadTestRun.objects.create(
            status=LoadTestRun.Status.RUNNING,
            expected_events=count,
            expected_unique_orders=unique_count,
            duplicate_events=duplicate_count,
        )
        self.stdout.write(f"Load-test run: {run.id}")
        self.stdout.write(
            f"Publishing {count} events ({unique_count} unique, "
            f"{duplicate_count} duplicates) to {stream_name}..."
        )

        events = generate_order_events(
            run_id=run.id,
            count=count,
            duplicate_count=duplicate_count,
            source=source,
            seed=options["seed"],
            started_at=run.started_at,
        )

        try:
            published = publish_events(
                client=client,
                stream_name=stream_name,
                events=events,
                batch_size=batch_size,
            )
        except (RedisError, OSError) as exc:
            run.status = LoadTestRun.Status.FAILED
            run.save(update_fields=("status",))
            raise CommandError(
                f"Publishing failed; run {run.id} was marked failed: {exc}"
            ) from exc
        finally:
            client.close()

        if published != count:
            run.status = LoadTestRun.Status.FAILED
            run.save(update_fields=("status",))
            raise CommandError(
                f"Expected to publish {count} events, but Redis returned {published} IDs"
            )

        run.status = LoadTestRun.Status.PROCESSING
        run.producer_finished_at = timezone.now()
        run.save(update_fields=("status", "producer_finished_at"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Published {published} events. Run {run.id} is ready for processing."
            )
        )
