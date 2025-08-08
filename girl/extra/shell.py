""""""

import asyncio
import json
import re
from logging import getLogger
from pprint import pformat
from typing import Callable
from typing import overload

from aiohttp import WSMsgType
from aiohttp import web

from ..world import Path
from ..world import World
from . import procs

_logger = getLogger(__name__)


@overload
async def shell(world: World, req: web.Request, /) -> web.StreamResponse: ...
@overload
async def shell(world: World, file: Path, /) -> None: ...


def _jsonrpcerr(id: object, code: int, message: str, data: ...):
    _logger.error(f"(in rpc processing) {message} %s", data)
    error = {"code": code, "message": message, "data": data}
    return {"jsonrpc": "2.0", "error": error, "id": id}


async def _jsonrpc(ws: web.WebSocketResponse, query: str):
    id: object = "yousk2"
    no_id = True
    try:
        rpc = json.loads(query)
        # HACK: prevent type narrowing wich causes a bunch of 'Unknown' types
        ty: ... = type(rpc)
        if ty is not dict:
            raise json.JSONDecodeError("expected an object", query, 0)
    except json.JSONDecodeError as e:
        data = {"pos": e.pos, "lineno": e.lineno, "colno": e.colno}
        await ws.send_json(_jsonrpcerr("yousk2", -32700, "Parse error", data))
        return

    if "id" in rpc:
        id = rpc["id"]
        no_id = False

    if "method" not in rpc or "params" not in rpc:
        data = f"no {'params' if 'method' in rpc else 'method'!r}"
        no_id or await ws.send_json(_jsonrpcerr(id, -32600, "Invalid Request", data))
        return

    name = str(rpc["method"])
    proc = getattr(procs, name, None)
    proc_params: dict[str, type] | None = getattr(proc, "_rpc_params", None)
    if proc is None or proc_params is None:
        no_id or await ws.send_json(_jsonrpcerr(id, -32601, "Method not found", name))
        return

    args = rpc["params"]
    ty = type(args)
    if ty is not dict or proc_params.keys() < args.keys():
        data = {"given": args, "expects": proc_params}
        no_id or await ws.send_json(_jsonrpcerr(id, -32602, "Invalid params", data))
        return

    try:
        ans = await proc(**args)
        # also in try as to catch serialization error
        no_id or await ws.send_json({"jsonrpc": "2.0", "result": ans, "id": id})
    except BaseException as e:
        data = f"{type(e).__name__}: {e}."
        no_id or await ws.send_json(_jsonrpcerr(id, -32603, "Internal error", data))


_NEXT_ARG = re.compile(r" +([_a-z]+)=(?:('[^']*')|(\S+))")
_TY_TL_TABLE: dict[type, Callable[[str], object]] = {
    str: str,
    int: int,
    float: float,
    list[str]: lambda s: s.split(","),
    list[int]: lambda s: map(int, s.split(",")),
    list[float]: lambda s: map(float, s.split(",")),
}


async def _clirpc(line: str) -> list[str]:
    name, space, rest = line.partition(" ")
    proc = getattr(procs, name, None)
    proc_params: dict[str, type] | None = getattr(proc, "_rpc_params", None)
    if proc is None or proc_params is None:
        return [f"No command {name!r}."]

    args = {str(g[1]): g[2] or g[3] for g in _NEXT_ARG.finditer(space + rest)}
    if proc_params.keys() < args.keys():
        return [
            "Wrong arguments;",
            f" * given: {args.keys()},",
            f" * expected: {proc_params.keys()}.",
        ]

    name = ""
    try:
        for name in args:
            args[name] = _TY_TL_TABLE[proc_params[name]](args[name])
    except ValueError as e:
        return [f"Bad argument {name!r} ({e})."]

    try:
        ans = await proc(**args)
    except BaseException as e:
        return [f"{type(e).__name__}: {e}."]

    return (ans if isinstance(ans, str) else pformat(ans)).splitlines()


async def shell(_world: World, arg: web.Request | Path, /) -> web.StreamResponse | None:
    """ """

    if isinstance(arg, web.Request):
        req = arg
        res = web.WebSocketResponse()
        await res.prepare(req)
        _logger.info("websocket connection established")

        async for msg in res:
            match msg.type:
                case WSMsgType.TEXT:
                    query = str(msg.data)
                case WSMsgType.BINARY:
                    query = bytes(msg.data).decode()
                case WSMsgType.ERROR:
                    _logger.warning("websocket exception %s", res.exception())
                    continue
                case _:
                    continue
            await _jsonrpc(res, query)

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

            async for line in r:
                line = line.decode().strip()
                w.writelines(l.encode() + b"\n" for l in await _clirpc(line))

            w.close()
            _logger.info("unix socket connection terminated")

        elif file.is_fifo():
            try:
                r = asyncio.StreamReader()
                protocol = asyncio.StreamReaderProtocol(r)
                loop = asyncio.get_event_loop()
                transport, _ = await loop.connect_read_pipe(lambda: protocol, file)
            finally:
                file.unlink()
            _logger.info("shell commands through fifo")

            async for line in r:
                line = line.decode().strip()
                await _clirpc(line)

            transport.close()
            assert not "implemented"

        else:
            _logger.info("shell commands through regular file")
            with file.open() as untracked:
                file.unlink()
                for line in untracked:
                    await _clirpc(line)
