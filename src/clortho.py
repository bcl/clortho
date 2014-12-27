import os
import asyncio
import signal
import argparse
import pickle
from aiohttp import web

VERSION = "0.1"
args = None
keystore = {}

@asyncio.coroutine
def get_version(request):
    text = "version: %s" % VERSION
    status = 200
    return web.Response(body=text.encode('utf-8'), status=status)

@asyncio.coroutine
def get_key(request):
    key = request.match_info.get('key')

    client = None
    if "X-Forwarded-For" in request.headers:
        client = request.headers["X-Forwarded-For"].split(",")[0]
    else:
        peername = request.transport.get_extra_info('peername')
        if peername is not None:
                client, _port = peername

    if client and client in keystore and key in keystore[client]:
        text = keystore[client][key]
        status = 200
    else:
        text = "%s doesn't exist for %s" % (key, client)
        status = 404
    return web.Response(body=text.encode('utf-8'), status=status)

@asyncio.coroutine
def set_key(request):
    key = request.match_info.get('key')
    post_data = yield from request.post()

    client = None
    if "X-Forwarded-For" in request.headers:
        client = request.headers["X-Forwarded-For"].split(",")[0]
    else:
        peername = request.transport.get_extra_info('peername')
        if peername is not None:
                client, _port = peername

    if client and key and "value" in post_data:
        if client not in keystore:
            keystore[client] = {}
        if post_data["value"]:
            keystore[client][key] = post_data["value"]
        else:
            del keystore[client][key]
        text = "OK"
        status = 200
    else:
        text = "ERROR"
        status = 404

    return web.Response(body=text.encode('utf-8'), status=status)

@asyncio.coroutine
def init(loop, host, port):
    app = web.Application(loop=loop)
    app.router.add_route('GET', '/keystore/version', get_version)
    app.router.add_route('GET', '/keystore/{key}', get_key)
    app.router.add_route('POST', '/keystore/{key}', set_key)

    srv = yield from loop.create_server(app.make_handler(), host, port)
    print("Server started at http://%s:%s" % (host, port))
    return srv

@asyncio.coroutine
def clean_exit(signame):
    print("got signal %s, exiting" % signame)
    save_keystore(args.keystore)

    loop = asyncio.get_event_loop()
    loop.stop()

def setup_parser():
    parser = argparse.ArgumentParser(description="Clortho key server")
    parser.add_argument("--host", default="127.0.0.1", help="Hostname or IP address to bind to")
    parser.add_argument("--port", default="9001", help="Port number to listen to")
    parser.add_argument("--keystore", default="clortho.dat", help="File to store keys in")

    return parser

def read_keystore(filename):
    if not os.path.exists(filename):
        return

    global keystore
    with open(filename, "rb") as f:
        try:
            keystore = pickle.load(f)
        except EOFError:
            keystore = {}

def save_keystore(filename):
    #TODO: Write to a tempfile first, rename to target
    with open(filename, "wb") as f:
        pickle.dump(keystore, f, pickle.HIGHEST_PROTOCOL)

if __name__=='__main__':
    parser = setup_parser()
    args = parser.parse_args()
    read_keystore(args.keystore)

    loop = asyncio.get_event_loop()
    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(getattr(signal, signame), asyncio.async, clean_exit(signame))
    loop.run_until_complete(init(loop, args.host, int(args.port)))
    loop.run_forever()
