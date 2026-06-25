# ActsOne Mini Project

## Run with Docker

Create the local environment file, update its secrets, then start the stack:

```bash
cp .env.example .env
docker compose up --build
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

To also remove PostgreSQL and Redis data:

```bash
docker compose down -v
```
