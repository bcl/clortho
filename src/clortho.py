# clortho - A simple key/value server
#
# Copyright 2014-2017 by Brian C. Lane <bcl@brianlane.com>
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
import os
import asyncio
import signal
import argparse
import pickle
from aiohttp import web

VERSION = "1.1.0"

def get_client(request):
    client = None
    if "X-Forwarded-For" in request.headers:
        client = request.headers["X-Forwarded-For"].split(",")[0]
        if client.startswith("::ffff:"):
            client = client[7:]
    else:
        peername = request.transport.get_extra_info('peername')
        if peername is not None:
                client, _port = peername
    return client

async def get_version(request):
    text = "version: %s" % VERSION
    status = 200
    return web.Response(text=text, status=status)

async def show_info(request):
    text = "<html><body><pre>\n"
    text += "\n".join("%s = %s" % (hdr, request.headers[hdr]) for hdr in request.headers)
    peername = request.transport.get_extra_info('peername')
    if peername is not None:
        text += "\npeer = %s:%s\n" % (peername[0], peername[1])
    text += "</pre></body></html>\n"

    return web.Response(text=text, content_type="text/html", status=200)

async def get_key(request):
    keystore = request.app["keystore"]
    key = request.match_info.get('key')

    client = get_client(request)
    if client and client in keystore and key in keystore[client]:
        text = keystore[client][key]
        status = 200
    else:
        text = "%s doesn't exist for %s" % (key, client)
        status = 404
    return web.Response(text=text, status=status)

async def set_key(request):
    keystore = request.app["keystore"]
    key = request.match_info.get('key')
    post_data = await request.post()

    client = get_client(request)
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

    return web.Response(text=text, status=status)

def setup_app(loop):
    app = web.Application(loop=loop)
    app.router.add_route('GET', '/keystore/version', get_version)
    app.router.add_route('GET', '/keystore/info', show_info)
    app.router.add_route('GET', '/keystore/{key}', get_key)
    app.router.add_route('POST', '/keystore/{key}', set_key)
    return app

async def init(loop, host, port, keystore):
    app = setup_app(loop)
    app["keystore"] = keystore
    srv = await loop.create_server(app.make_handler(), host, port)
    print("Server started at http://%s:%s" % (host, port))
    return srv

def setup_parser():
    parser = argparse.ArgumentParser(description="Clortho key server")
    parser.add_argument("--host", default="127.0.0.1", help="Hostname or IP address to bind to")
    parser.add_argument("--port", default="9001", help="Port number to listen to")
    parser.add_argument("--keystore", default="clortho.dat", help="File to store keys in")

    return parser

def read_keystore(filename):
    if not os.path.exists(filename):
        return {}

    with open(filename, "rb") as f:
        try:
            return pickle.load(f)
        except EOFError:
            return {}

def clean_exit(signame, loop, filename, keystore):
    print("got signal %s, exiting" % signame)
    save_keystore(filename, keystore)

    loop.stop()

def handle_usr1(filename, keystore):
    print("Got USR1 signal, saving keystore")
    save_keystore(filename, keystore)

def hourly_save_keystore(loop, filename, keystore):
    save_keystore(filename, keystore)
    loop.call_later(3600, hourly_save_keystore, loop)

def save_keystore(filename, keystore):
    #TODO: Write to a tempfile first, rename to target
    with open(filename, "wb") as f:
        pickle.dump(keystore, f, pickle.HIGHEST_PROTOCOL)

if __name__=='__main__':
    parser = setup_parser()
    args = parser.parse_args()
    keystore = read_keystore(args.keystore)

    loop = asyncio.get_event_loop()
    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(getattr(signal, signame), clean_exit, *[signame, loop, args.keystore, keystore])
    loop.add_signal_handler(getattr(signal, 'SIGUSR1'), handle_usr1, *[args.keystore, keystore])

    # Start saving the keys every hour
    loop.call_later(3600, hourly_save_keystore, loop, args.keystore, keystore)

    loop.run_until_complete(init(loop, args.host, int(args.port), keystore))
    loop.run_forever()
