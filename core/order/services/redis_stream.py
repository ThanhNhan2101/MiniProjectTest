from collections.abc import Iterable, Mapping

from django.conf import settings
from redis import Redis


def get_redis_client() -> Redis:
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
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
