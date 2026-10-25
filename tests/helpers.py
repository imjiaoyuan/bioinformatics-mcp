import unittest
from unittest.mock import patch

import httpx

from common import http


class HTTPTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        http._locks.clear()
        http._last_request.clear()

    def mock_http(self, handler):
        client_type = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        return patch("httpx.AsyncClient", side_effect=lambda **kw: client_type(transport=transport, **kw))
