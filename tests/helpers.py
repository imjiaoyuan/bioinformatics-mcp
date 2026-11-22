import unittest
from unittest.mock import patch

import httpx

from common import api, http


class HTTPTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        http._locks.clear()
        http._next_slot.clear()
        api._cache.clear()

    def mock_http(self, handler):
        client_type = httpx.AsyncClient
        transport = httpx.MockTransport(handler)
        from contextlib import ExitStack
        stack = ExitStack()

        def build(**options):
            options.pop("http2", None)
            return client_type(transport=transport, **options)
        stack.enter_context(patch("httpx.AsyncClient", side_effect=build))
        # The shared client caches its transport; force a rebuild for each mock.
        stack.enter_context(patch.object(http, "_client", None))
        return stack
