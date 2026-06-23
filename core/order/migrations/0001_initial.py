import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="LoadTestRun",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("expected_events", models.PositiveBigIntegerField()),
                ("expected_unique_orders", models.PositiveBigIntegerField()),
                ("duplicate_events", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                (
                    "producer_finished_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "load_test_runs",
                "ordering": ("-started_at",),
                "indexes": [
                    models.Index(
                        fields=["status", "-started_at"],
                        name="run_status_started_idx",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            expected_unique_orders__lte=models.F("expected_events")
                        ),
                        name="run_unique_orders_lte_events",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(producer_finished_at__isnull=True)
                        | models.Q(
                            producer_finished_at__gte=models.F("started_at")
                        ),
                        name="run_producer_finish_after_start",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(completed_at__isnull=True)
                        | models.Q(completed_at__gte=models.F("started_at")),
                        name="run_complete_after_start",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("order_id", models.CharField(max_length=64)),
                ("status", models.CharField(db_index=True, max_length=32)),
                ("last_event_at", models.DateTimeField()),
                ("last_event_id", models.UUIDField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="orders",
                        to="order.loadtestrun",
                    ),
                ),
            ],
            options={
                "db_table": "orders",
                "ordering": ("-last_event_at",),
                "indexes": [
                    models.Index(
                        fields=["run", "status"],
                        name="order_run_status_idx",
                    ),
                    models.Index(
                        fields=["run", "-last_event_at"],
                        name="order_run_event_at_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("run", "order_id"),
                        name="unique_order_per_run",
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(order_id=""),
                        name="order_id_not_empty",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ProcessingFailure",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("event_id", models.UUIDField()),
                ("stream_entry_id", models.CharField(max_length=64)),
                ("error_type", models.CharField(db_index=True, max_length=128)),
                ("error_message", models.TextField()),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processing_failures",
                        to="order.loadtestrun",
                    ),
                ),
            ],
            options={
                "db_table": "processing_failures",
                "ordering": ("created_at",),
                "indexes": [
                    models.Index(
                        fields=["run", "resolved_at"],
                        name="failure_run_resolved_idx",
                    ),
                    models.Index(
                        fields=["run", "created_at"],
                        name="failure_run_created_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("run", "event_id"),
                        name="unique_failure_event_per_run",
                    ),
                    models.UniqueConstraint(
                        fields=("run", "stream_entry_id"),
                        name="unique_failure_stream_per_run",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ProcessedEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("event_id", models.UUIDField()),
                ("stream_entry_id", models.CharField(max_length=64)),
                (
                    "result",
                    models.CharField(
                        choices=[
                            ("created", "Order created"),
                            ("updated", "Order updated"),
                            ("duplicate", "Duplicate skipped"),
                            ("stale", "Stale event skipped"),
                        ],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("occurred_at", models.DateTimeField()),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_events",
                        to="order.order",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processed_events",
                        to="order.loadtestrun",
                    ),
                ),
            ],
            options={
                "db_table": "processed_events",
                "ordering": ("processed_at",),
                "indexes": [
                    models.Index(
                        fields=["run", "processed_at"],
                        name="event_run_processed_idx",
                    ),
                    models.Index(
                        fields=["run", "result"],
                        name="event_run_result_idx",
                    ),
                    models.Index(
                        fields=["order", "-occurred_at"],
                        name="event_order_occurred_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("run", "event_id"),
                        name="unique_event_per_run",
                    ),
                    models.UniqueConstraint(
                        fields=("run", "stream_entry_id"),
                        name="unique_stream_entry_per_run",
                    ),
                ],
            },
        ),
    ]
