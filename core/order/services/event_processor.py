import uuid
from dataclasses import dataclass
from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from core.order.models import LoadTestRun, Order, ProcessedEvent
from core.order.services.producer import ORDER_STATUSES


class EventPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class OrderEvent:
    event_id: uuid.UUID
    run_id: uuid.UUID
    order_id: str
    status: str
    occurred_at: datetime


@dataclass(frozen=True)
class ProcessEventResult:
    event_id: uuid.UUID
    order_id: str
    result: str
    already_processed: bool = False


def parse_order_event(payload: dict[str, str]) -> OrderEvent:
    missing_fields = [
        field
        for field in ("event_id", "run_id", "order_id", "status", "occurred_at")
        if not payload.get(field)
    ]
    if missing_fields:
        raise EventPayloadError(f"Missing required fields: {', '.join(missing_fields)}")

    try:
        event_id = uuid.UUID(payload["event_id"])
        run_id = uuid.UUID(payload["run_id"])
    except ValueError as exc:
        raise EventPayloadError("event_id and run_id must be valid UUID values") from exc

    order_id = payload["order_id"].strip()
    if not order_id:
        raise EventPayloadError("order_id cannot be empty")

    status = payload["status"].strip().upper()
    if status not in ORDER_STATUSES:
        raise EventPayloadError(f"Unsupported order status: {status}")

    occurred_at = parse_datetime(payload["occurred_at"])
    if occurred_at is None:
        raise EventPayloadError("occurred_at must be an ISO-8601 datetime")
    if timezone.is_naive(occurred_at):
        occurred_at = timezone.make_aware(occurred_at, timezone=timezone.utc)

    return OrderEvent(
        event_id=event_id,
        run_id=run_id,
        order_id=order_id,
        status=status,
        occurred_at=occurred_at,
    )


def process_order_event(
    *,
    stream_entry_id: str,
    payload: dict[str, str],
) -> ProcessEventResult:
    event = parse_order_event(payload)

    with transaction.atomic():
        run = LoadTestRun.objects.get(id=event.run_id)
        existing_event = ProcessedEvent.objects.filter(
            run=run,
            event_id=event.event_id,
        ).select_related("order").first()
        if existing_event is not None:
            return ProcessEventResult(
                event_id=event.event_id,
                order_id=existing_event.order.order_id,
                result=ProcessedEvent.Result.DUPLICATE,
                already_processed=True,
            )

        order = (
            Order.objects.select_for_update()
            .filter(run=run, order_id=event.order_id)
            .first()
        )

        if order is None:
            order = Order.objects.create(
                run=run,
                order_id=event.order_id,
                status=event.status,
                last_event_at=event.occurred_at,
                last_event_id=event.event_id,
            )
            result = ProcessedEvent.Result.CREATED
        elif event.occurred_at < order.last_event_at:
            result = ProcessedEvent.Result.STALE
        else:
            order.status = event.status
            order.last_event_at = event.occurred_at
            order.last_event_id = event.event_id
            order.save(update_fields=("status", "last_event_at", "last_event_id", "updated_at"))
            result = ProcessedEvent.Result.UPDATED

        try:
            with transaction.atomic():
                ProcessedEvent.objects.create(
                    run=run,
                    order=order,
                    event_id=event.event_id,
                    stream_entry_id=stream_entry_id,
                    result=result,
                    occurred_at=event.occurred_at,
                )
        except IntegrityError:
            existing_event = ProcessedEvent.objects.filter(
                run=run,
                event_id=event.event_id,
            ).select_related("order").first()
            if existing_event is None:
                existing_event = ProcessedEvent.objects.get(
                    run=run,
                    stream_entry_id=stream_entry_id,
                )
            return ProcessEventResult(
                event_id=event.event_id,
                order_id=existing_event.order.order_id,
                result=ProcessedEvent.Result.DUPLICATE,
                already_processed=True,
            )

    return ProcessEventResult(
        event_id=event.event_id,
        order_id=event.order_id,
        result=result,
    )
