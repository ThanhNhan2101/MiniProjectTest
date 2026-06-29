from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.order.models import LoadTestRun
from core.order.services.stats import build_stats_response, get_latest_run


class OrderStatsAPIView(APIView):
    def get(self, request):
        run_id = request.query_params.get("run_id")
        group_name = request.query_params.get("group", "order-workers")
        stream_name = request.query_params.get("stream", settings.REDIS_ORDER_STREAM)

        if run_id:
            try:
                run = LoadTestRun.objects.get(id=run_id)
            except (LoadTestRun.DoesNotExist, ValueError):
                return Response(
                    {"detail": "Load-test run was not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            run = get_latest_run()
            if run is None:
                return Response(
                    {"detail": "No load-test run exists yet."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        return Response(
            build_stats_response(
                run=run,
                stream_name=stream_name,
                group_name=group_name,
            )
        )
