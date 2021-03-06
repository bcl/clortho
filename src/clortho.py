# clortho - A simple key/value server
#
# Copyright 2014-2018 by Brian C. Lane <bcl@brianlane.com>
# All Rights Reserved
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# Author(s): Brian C. Lane <bcl@brianlane.com>
#
from typing import cast, Tuple, Dict

import os
import asyncio
from asyncio.base_events import Server
from asyncio import AbstractEventLoop
import signal
from argparse import ArgumentParser, Namespace
import pickle
from aiohttp import web

KeystoreType = Dict[str, Dict[str, str]]

VERSION = "1.1.0"   # type: str

def get_client(request: web.Request) -> str:
    client = ""   # type: str
    if "X-Forwarded-For" in request.headers:
        client = request.headers["X-Forwarded-For"].split(",")[0]
        if client.startswith("::ffff:"):
            client = client[7:]
    else:
        peername = request.transport.get_extra_info('peername')     # type: Tuple[str, str]
        if peername is not None:
            client, _port = peername
    return client

async def get_version(request: web.Request) -> web.Response:
    text = "version: %s" % VERSION
    status = 200
    return web.Response(text=text, status=status)

async def show_info(request: web.Request) -> web.Response:
    text = "<html><body><pre>\n"
    text += "\n".join("%s = %s" % (hdr, request.headers[hdr]) for hdr in request.headers)
    peername = request.transport.get_extra_info('peername')
    if peername is not None:
        text += "\npeer = %s:%s\n" % (peername[0], peername[1])
    text += "</pre></body></html>\n"

    return web.Response(text=text, content_type="text/html", status=200)

async def get_key(request: web.Request) -> web.Response:
    keystore = request.app["keystore"]      # type: KeystoreType
    key = request.match_info.get('key')     # type: str

    client = get_client(request)            # type: str
    if client in keystore and key in keystore[client]:
        text = keystore[client][key]        # type: str
        status = 200                        # type: int
    else:
        text = "%s doesn't exist for %s" % (key, client)
        status = 404
    return web.Response(text=text, status=status)

async def set_key(request: web.Request) -> web.Response:
    keystore = request.app["keystore"]      # type: KeystoreType
    key = request.match_info.get('key')     # type: str
    post_data = await request.post()        # type: Dict[str, str]

    client = get_client(request)            # type: str
    if client != "" and key != "" and "value" in post_data:
        if client not in keystore:
            keystore[client] = {}
        if post_data["value"] is not None:
            keystore[client][key] = post_data["value"]
        else:
            del keystore[client][key]
        text = "OK"                         # type: str
        status = 200                        # type: int
    else:
        text = "ERROR"
        status = 404

    return web.Response(text=text, status=status)

def setup_app(loop: AbstractEventLoop) -> web.Application:
    app = web.Application(loop=loop)
    app.router.add_route('GET', '/keystore/version', get_version)
    app.router.add_route('GET', '/keystore/info', show_info)
    app.router.add_route('GET', '/keystore/{key}', get_key)
    app.router.add_route('POST', '/keystore/{key}', set_key)
    return app

async def init(loop: AbstractEventLoop, host: str, port: int, keystore: KeystoreType) -> Server:
    app = setup_app(loop)
    app["keystore"] = keystore
    srv = await loop.create_server(app.make_handler(), host, port)
    print("Server started at http://%s:%s" % (host, port))
    return srv

def setup_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Clortho key server")
    parser.add_argument("--host", default="127.0.0.1", help="Hostname or IP address to bind to")
    parser.add_argument("--port", default="9001", help="Port number to listen to")
    parser.add_argument("--keystore", default="clortho.dat", help="File to store keys in")

    return parser

def read_keystore(filename: str) -> KeystoreType:
    if not os.path.exists(filename):
        return {}

    with open(filename, "rb") as f:
        try:
            return cast(KeystoreType, pickle.load(f))
        except EOFError:
            return {}

def clean_exit(signame: str, loop: AbstractEventLoop, filename: str, keystore: Dict[str, Dict[str, str]]) -> None:
    print("got signal %s, exiting" % signame)
    save_keystore(filename, keystore)

    loop.stop()

def handle_usr1(filename: str, keystore: Dict[str, Dict[str, str]]) -> None:
    print("Got USR1 signal, saving keystore")
    save_keystore(filename, keystore)

def hourly_save_keystore(loop: AbstractEventLoop, filename: str, keystore: Dict[str, Dict[str, str]]) -> None:
    save_keystore(filename, keystore)
    loop.call_later(3600, hourly_save_keystore, loop, filename, keystore)

def save_keystore(filename: str, keystore: Dict[str, Dict[str, str]]) -> None:
    #TODO: Write to a tempfile first, rename to target
    with open(filename, "wb") as f:
        pickle.dump(keystore, f, pickle.HIGHEST_PROTOCOL)

def main(args: Namespace) -> None:
    keystore = read_keystore(args.keystore)

    loop = asyncio.get_event_loop()
    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(getattr(signal, signame), clean_exit, *[signame, loop, args.keystore, keystore])
    loop.add_signal_handler(getattr(signal, 'SIGUSR1'), handle_usr1, *[args.keystore, keystore])

    # Start saving the keys every hour
    loop.call_later(3600, hourly_save_keystore, loop, args.keystore, keystore)

    loop.run_until_complete(init(loop, args.host, int(args.port), keystore))
    loop.run_forever()

if __name__ == '__main__':
    main(setup_parser().parse_args())
