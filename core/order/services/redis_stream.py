from collections.abc import Iterable, Mapping

from django.conf import settings
from redis import Redis
from redis.exceptions import ResponseError


def get_redis_client() -> Redis:
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=10,
        socket_timeout=30,
        health_check_interval=30,
    )


def publish_events(
    client: Redis,
    stream_name: str,
    events: Iterable[Mapping[str, str]],
    batch_size: int,
) -> int:
    published = 0
    pipeline = client.pipeline(transaction=False)
    queued = 0

    for event in events:
        pipeline.xadd(stream_name, event)
        queued += 1

        if queued == batch_size:
            published += len(pipeline.execute())
            pipeline = client.pipeline(transaction=False)
            queued = 0

    if queued:
        published += len(pipeline.execute())

    return published


def ensure_consumer_group(client: Redis, stream_name: str, group_name: str) -> None:
    try:
        client.xgroup_create(
            name=stream_name,
            groupname=group_name,
            id="0",
            mkstream=True,
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def read_group(
    client: Redis,
    stream_name: str,
    group_name: str,
    consumer_name: str,
    count: int,
    block_ms: int,
) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
    return client.xreadgroup(
        groupname=group_name,
        consumername=consumer_name,
        streams={stream_name: ">"},
        count=count,
        block=block_ms,
    )


def acknowledge_events(
    client: Redis,
    stream_name: str,
    group_name: str,
    stream_entry_ids: Iterable[str],
) -> int:
    entry_ids = list(stream_entry_ids)
    if not entry_ids:
        return 0

    return client.xack(stream_name, group_name, *entry_ids)
