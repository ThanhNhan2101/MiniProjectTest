import random
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta


ORDER_STATUSES = (
    "CREATED",
    "CONFIRMED",
    "READY_TO_SHIP",
    "SHIPPED",
)


def calculate_duplicate_count(count: int, duplicate_rate: float) -> int:
    if count < 1:
        raise ValueError("count must be at least 1")
    if not 0 <= duplicate_rate < 1:
        raise ValueError("duplicate_rate must be greater than or equal to 0 and less than 1")

    return int(count * duplicate_rate)


def generate_order_events(
    *,
    run_id: uuid.UUID,
    count: int,
    duplicate_count: int,
    source: str,
    seed: int,
    started_at: datetime,
) -> Iterator[dict[str, str]]:
    unique_count = count - duplicate_count
    if unique_count < 1:
        raise ValueError("at least one unique order is required")

    randomizer = random.Random(seed)
    order_prefix = str(run_id).split("-", maxsplit=1)[0].upper()
    unique_order_ids = [
        f"{source.upper()}-{order_prefix}-{index:08d}"
        for index in range(1, unique_count + 1)
    ]
    event_orders = [(order_id, False) for order_id in unique_order_ids]
    event_orders.extend(
        (randomizer.choice(unique_order_ids), True)
        for _ in range(duplicate_count)
    )
    randomizer.shuffle(event_orders)

    for sequence, (order_id, is_duplicate) in enumerate(event_orders, start=1):
        event_id = uuid.uuid5(run_id, f"event:{sequence}")
        occurred_at = started_at + timedelta(milliseconds=sequence)
        yield {
            "event_id": str(event_id),
            "run_id": str(run_id),
            "order_id": order_id,
            "status": randomizer.choice(ORDER_STATUSES),
            "occurred_at": occurred_at.isoformat(),
            "source": source,
            "payload_version": "1",
            "sequence": str(sequence),
            "is_duplicate": "1" if is_duplicate else "0",
        }
