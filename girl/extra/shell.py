""""""

import asyncio
import json
from logging import getLogger
from typing import overload

from aiohttp import WSMsgType
from aiohttp import web

from ..app import App
from ..events.file import Path
from ..world import World
from . import procs
from .procs import Interact

_logger = getLogger(__name__)


@overload
async def shell(world: World, req: web.Request, /) -> web.StreamResponse: ...
@overload
async def shell(world: World, file: Path, /) -> None: ...


async def _rpc(req: str, app: App, io: Interact) -> object:
    rpc: list[str] = json.loads(req)
    name, *args = rpc
    return await getattr(procs, name)(*args, app=app, io=io)


async def shell(world: World, arg: web.Request | Path, /) -> web.StreamResponse | None:
    """ """

    if isinstance(arg, web.Request):
        req = arg
        res = web.WebSocketResponse()
        await res.prepare(req)
        _logger.info("websocket connection established")

        try:
            async for msg in res:
                match msg.type:
                    case WSMsgType.BINARY:
                        io = Interact(res.receive_bytes, res.send_bytes)
                        await res.send_json(await _rpc(str(msg.data), world.app, io))
                    case WSMsgType.ERROR:
                        _logger.warning("websocket exception %s", res.exception())
                    case _:
                        pass

        except:
            await res.close()
            raise
        _logger.info("websocket connection terminated")
        return res

    elif isinstance(arg, Path):
        file = arg
        if file.is_socket():
            try:
                r, w = await asyncio.open_unix_connection(file)
            finally:
                file.unlink()
            _logger.info("unix socket connection established")

            io = Interact(r.readline, lambda data: w.write(data) or w.drain())
            try:
                async for line in r:
                    line = line.decode().strip()
                    w.write(f"{json.dumps(await _rpc(line, world.app, io))}\n".encode())
                    await w.drain()

            finally:
                w.close()
            _logger.info("unix socket connection terminated")

        elif file.is_fifo():
            try:
                pipe = file.open()
                r = asyncio.StreamReader()
                f = lambda: asyncio.StreamReaderProtocol(r)
                transport, _ = await asyncio.get_event_loop().connect_read_pipe(f, pipe)
                _logger.info("shell commands through fifo")
            finally:
                file.unlink()

            ix = Interact(r.readline, None)
            try:
                async for line in r:
                    line = line.decode().strip()
                    ans = json.dumps(await _rpc(line, world.app, ix))
                    _logger.info("query: %s, ans: %s", line.strip(), ans)

            finally:
                _logger.info("shell commands through fifo done")
                transport.close()
                pipe.close()

        else:
            _logger.info("unsupported shell file type %s", file.stat())
            file.unlink()
