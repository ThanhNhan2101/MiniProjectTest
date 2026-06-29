# ActsOne Mini Project

## Run with Docker

Create the local environment file, update its secrets, then start the stack:

```bash
cp .env.example .env
docker compose up -d --build
```

The services are available at:

- Django: http://localhost:8000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

Useful commands:

```bash
docker compose exec backend python manage.py createsuperuser
docker compose logs -f backend
docker compose down
```

Publish a reproducible load-test run to Redis Streams:

```bash
docker compose exec backend python manage.py produce_orders \
  --count 50000 \
  --duplicate-rate 0.15 \
  --batch-size 500 \
  --seed 42
```

The command creates a `LoadTestRun`, publishes the events to
`REDIS_ORDER_STREAM`, and prints the run ID that workers will process.

Consume events from Redis Streams and write orders to PostgreSQL:

```bash
docker compose exec backend python manage.py consume_orders \
  --stream orders-stream \
  --group order-workers \
  --consumer worker-1 \
  --count 100 \
  --block-ms 5000
```

The worker uses `XREADGROUP`, writes each event in a database transaction,
then calls `XACK` only after the database work succeeds.

View processing stats:

```bash
curl http://localhost:8000/api/orders/stats/
curl "http://localhost:8000/api/orders/stats/?run_id=<run-id>"
```

The response combines PostgreSQL counters with Redis Stream metadata, including
stream length, consumer group state, pending messages, processed events, and
remaining events.

To also remove PostgreSQL and Redis data:

```bash
docker compose down -v
```
