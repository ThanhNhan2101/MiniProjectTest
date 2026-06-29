from django.urls import path

from core.order.endpoints.api import OrderStatsAPIView


urlpatterns = [
    path("stats/", OrderStatsAPIView.as_view(), name="order-stats"),
]
