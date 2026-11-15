import unittest
from unittest.mock import patch

import httpx

from common import http


class HTTPTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        http._locks.clear()
        http._next_slot.clear()

    def mock_http(self, handler):
        client_type = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch("httpx.AsyncClient",
                                  side_effect=lambda **kw: client_type(transport=transport, **kw)))
        # The shared client caches its transport; force a rebuild for each mock.
        stack.enter_context(patch.object(http, "_client", None))
        return stack
