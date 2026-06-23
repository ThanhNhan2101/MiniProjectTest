import uuid

from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError


class LoadTestRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default= uuid.uuid4, editable= False)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    expected_events = models.PositiveBigIntegerField()
    expected_unique_orders = models.PositiveBigIntegerField()
    duplicate_events = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    producer_finished_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "load_test_runs"
        ordering = ("-started_at",)
        indexes = [
            models.Index(
                fields=("status", "-started_at"),
                name="run_status_started_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(expected_unique_orders__lte=models.F("expected_events")),
                name="run_unique_orders_lte_events",
            ),
            models.CheckConstraint(
                condition=Q(producer_finished_at__isnull=True)
                | Q(producer_finished_at__gte=models.F("started_at")),
                name="run_producer_finish_after_start",
            ),
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True)
                | Q(completed_at__gte=models.F("started_at")),
                name="run_complete_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.id} ({self.status})"


class Order(models.Model):
    run = models.ForeignKey(
        LoadTestRun,
        on_delete=models.CASCADE,
        related_name="orders",
    )
    order_id = models.CharField(max_length=64)
    status = models.CharField(max_length=32, db_index=True)
    last_event_at = models.DateTimeField()
    last_event_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "orders"
        ordering = ("-last_event_at",)
        indexes = [
            models.Index(
                fields=("run", "status"),
                name="order_run_status_idx",
            ),
            models.Index(
                fields=("run", "-last_event_at"),
                name="order_run_event_at_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("run", "order_id"),
                name="unique_order_per_run",
            ),
            models.CheckConstraint(
                condition=~Q(order_id=""),
                name="order_id_not_empty",
            ),
        ]

    def __str__(self):
        return f"{self.run_id}:{self.order_id}"


class ProcessedEvent(models.Model):
    class Result(models.TextChoices):
        CREATED = "created", "Order created"
        UPDATED = "updated", "Order updated"
        DUPLICATE = "duplicate", "Duplicate skipped"
        STALE = "stale", "Stale event skipped"

    run = models.ForeignKey(
        LoadTestRun,
        on_delete=models.CASCADE,
        related_name="processed_events",
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="processed_events",
    )
    event_id = models.UUIDField()
    stream_entry_id = models.CharField(max_length=64)
    result = models.CharField(max_length=16, choices=Result.choices, db_index=True)
    occurred_at = models.DateTimeField()
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "processed_events"
        ordering = ("processed_at",)
        indexes = [
            models.Index(
                fields=("run", "processed_at"),
                name="event_run_processed_idx",
            ),
            models.Index(
                fields=("run", "result"),
                name="event_run_result_idx",
            ),
            models.Index(
                fields=("order", "-occurred_at"),
                name="event_order_occurred_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("run", "event_id"),
                name="unique_event_per_run",
            ),
            models.UniqueConstraint(
                fields=("run", "stream_entry_id"),
                name="unique_stream_entry_per_run",
            ),
        ]

    def __str__(self):
        return f"{self.event_id} ({self.result})"
    
    def clean(self):
        super().clean()
        if (
            self.order_id
            and self.run_id
            and self.run_id != self.order.run_id
        ):
            raise ValidationError("Order must belong load-test run.")


class ProcessingFailure(models.Model):
    run = models.ForeignKey(
        LoadTestRun,
        on_delete=models.CASCADE,
        related_name="processing_failures",
    )
    event_id = models.UUIDField()
    stream_entry_id = models.CharField(max_length=64)
    error_type = models.CharField(max_length=128, db_index=True)
    error_message = models.TextField()
    retry_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "processing_failures"
        ordering = ("created_at",)
        indexes = [
            models.Index(
                fields=("run", "resolved_at"),
                name="failure_run_resolved_idx",
            ),
            models.Index(
                fields=("run", "created_at"),
                name="failure_run_created_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("run", "event_id"),
                name="unique_failure_event_per_run",
            ),
            models.UniqueConstraint(
                fields=("run", "stream_entry_id"),
                name="unique_failure_stream_per_run",
            ),
        ]


    @property
    def is_resolved(self):
        return self.resolved_at is not None

    def __str__(self):
        return f"{self.event_id} ({self.error_type})"
