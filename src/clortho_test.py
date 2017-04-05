#!/usr/bin/python3

import pytest
from aiohttp.test_utils import make_mocked_request

from clortho import get_client, setup_app, VERSION

@pytest.fixture
def cli(loop, test_client):
    app = setup_app(loop)
    app["keystore"] = {}
    return loop.run_until_complete(test_client(app))

async def test_version(cli):
    resp = await cli.get("/keystore/version")
    assert resp.status == 200
    assert await resp.text() == "version: %s" % VERSION

async def test_post(cli):
    resp = await cli.post("/keystore/test", data={"value": "test value"})
    assert resp.status == 200
    assert await resp.text() == "OK"

async def test_get(cli):
    resp = await cli.post("/keystore/test-get", data={"value": "test-get value"})
    assert resp.status == 200
    assert await resp.text() == "OK"

    resp = await cli.get("/keystore/test-get")
    assert resp.status == 200
    assert await resp.text() == "test-get value"

async def test_info(cli):
    resp = await cli.get("/keystore/info")
    assert resp.status == 200

def test_proxy_client():
    req = make_mocked_request("GET", "/keystore/version", headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
    client = get_client(req)
    assert client == "1.2.3.4"

def test_client_peer():
    class MockTransport(object):
        def get_extra_info(self, ignore):
            return ("1.2.3.4", 65535)

    req = make_mocked_request("GET", "/keystore/version", transport=MockTransport())
    client = get_client(req)
    assert client == "1.2.3.4"
