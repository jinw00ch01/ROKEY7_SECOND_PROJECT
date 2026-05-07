import pytest

try:
    from cobot_task_manager.order_provider import DBOrderProvider
except ModuleNotFoundError:
    from cobot_task_manager.cobot_task_manager.order_provider import DBOrderProvider


class _Request:
    pass


class _ServiceType:
    Request = _Request


class _Response:
    def __init__(
        self,
        success=True,
        message="",
        almond=1,
        cashew=2,
        pistachio=3,
        walnut=4,
    ):
        self.success = success
        self.message = message
        self.almond = almond
        self.cashew = cashew
        self.pistachio = pistachio
        self.walnut = walnut


class _DoneFuture:
    def __init__(self, response):
        self._response = response

    def done(self):
        return True

    def result(self):
        return self._response


class _NeverFuture:
    def done(self):
        return False


class _Client:
    def __init__(self, service_available=True, future=None):
        self.service_available = service_available
        self.future = future or _DoneFuture(_Response())
        self.requests = []

    def wait_for_service(self, timeout_sec):
        return self.service_available

    def call_async(self, request):
        self.requests.append(request)
        return self.future


class _Node:
    def __init__(self, client):
        self.client = client
        self.created = []

    def create_client(self, service_type, service_name):
        self.created.append((service_type, service_name))
        return self.client


def _provider(client, **kwargs):
    return DBOrderProvider(
        node=_Node(client),
        service_name="/db/get_nut_order",
        timeout_sec=0.01,
        service_type=_ServiceType,
        poll_sec=0.0,
        **kwargs,
    )


def test_db_order_provider_fetches_counts():
    provider = _provider(_Client(future=_DoneFuture(_Response())))

    order = provider.fetch()

    assert order.counts == {
        "almond": 1,
        "cashew": 2,
        "pistachio": 3,
        "walnut": 4,
    }


def test_db_order_provider_rejects_unavailable_service():
    provider = _provider(_Client(service_available=False))

    with pytest.raises(RuntimeError, match="not available"):
        provider.fetch()


def test_db_order_provider_rejects_failed_response():
    provider = _provider(
        _Client(future=_DoneFuture(_Response(success=False, message="db down")))
    )

    with pytest.raises(RuntimeError, match="db down"):
        provider.fetch()


def test_db_order_provider_times_out_without_spinning_node():
    provider = _provider(_Client(future=_NeverFuture()))

    with pytest.raises(RuntimeError, match="call timed out"):
        provider.fetch()


def test_db_order_provider_stop_callback_interrupts_wait():
    provider = _provider(_Client(future=_NeverFuture()), should_stop=lambda: True)

    with pytest.raises(RuntimeError, match="call timed out"):
        provider.fetch()
