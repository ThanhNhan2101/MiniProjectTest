from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db.models import Count
from redis.exceptions import RedisError

from core.order.models import LoadTestRun, Order, ProcessedEvent, ProcessingFailure
from core.order.services.redis_stream import get_redis_client


def     get_latest_run() -> LoadTestRun | None:
    return LoadTestRun.objects.order_by("-started_at").first()


def get_run_stats(run: LoadTestRun) -> dict:
    result_counts = {
        item["result"]: item["total"]
        for item in ProcessedEvent.objects.filter(run=run)
        .values("result")
        .annotate(total=Count("id"))
    }
    processed_total = sum(result_counts.values())
    progress = Decimal(0)
    if run.expected_events:
        progress = (Decimal(processed_total) / Decimal(run.expected_events) * 100).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    return {
        "run": {
            "id": str(run.id),
            "status": run.status,
            "expected_events": run.expected_events,
            "expected_unique_orders": run.expected_unique_orders,
            "duplicate_events": run.duplicate_events,
            "started_at": run.started_at,
            "producer_finished_at": run.producer_finished_at,
            "completed_at": run.completed_at,
        },
        "database": {
            "orders_total": Order.objects.filter(run=run).count(),
            "processed_events_total": processed_total,
            "failures_total": ProcessingFailure.objects.filter(run=run).count(),
            "results": {
                ProcessedEvent.Result.CREATED: result_counts.get(
                    ProcessedEvent.Result.CREATED,
                    0,
                ),
                ProcessedEvent.Result.UPDATED: result_counts.get(
                    ProcessedEvent.Result.UPDATED,
                    0,
                ),
                ProcessedEvent.Result.DUPLICATE: result_counts.get(
                    ProcessedEvent.Result.DUPLICATE,
                    0,
                ),
                ProcessedEvent.Result.STALE: result_counts.get(
                    ProcessedEvent.Result.STALE,
                    0,
                ),
            },
            "progress_percent": float(progress),
            "remaining_events": max(run.expected_events - processed_total, 0),
        },
    }


def get_redis_stats(
    *,
    stream_name: str | None = None,
    group_name: str = "order-workers",
) -> dict:
    stream_name = stream_name or settings.REDIS_ORDER_STREAM
    client = get_redis_client()

    try:
        stream_info = client.xinfo_stream(stream_name)
        groups = client.xinfo_groups(stream_name)
    except RedisError as exc:
        return {
            "available": False,
            "stream": stream_name,
            "group": group_name,
            "error": str(exc),
        }
    finally:
        client.close()

    target_group = next(
        (group for group in groups if group.get("name") == group_name),
        None,
    )

    return {
        "available": True,
        "stream": stream_name,
        "length": stream_info.get("length", 0),
        "first_entry_id": stream_info.get("first-entry", [None])[0],
        "last_entry_id": stream_info.get("last-entry", [None])[0],
        "group": {
            "name": group_name,
            "exists": target_group is not None,
            "consumers": target_group.get("consumers", 0) if target_group else 0,
            "pending": target_group.get("pending", 0) if target_group else 0,
            "last_delivered_id": (
                target_group.get("last-delivered-id") if target_group else None
            ),
        },
    }


def build_stats_response(
    *,
    run: LoadTestRun,
    stream_name: str | None = None,
    group_name: str = "order-workers",
) -> dict:
    stats = get_run_stats(run)
    stats["redis"] = get_redis_stats(
        stream_name=stream_name,
        group_name=group_name,
    )
    return stats
