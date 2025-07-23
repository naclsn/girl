from collections.abc import AsyncGenerator
from collections.abc import Awaitable
from typing import Callable
from typing import Literal

from aiohttp import web

from .world import Path
from .world import World

MethodStr = Literal[
    "*",
    "CONNECT",
    "HEAD",
    "GET",
    "DELETE",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
    "TRACE",
]

HttpHandler = (
    Callable[[World, web.Request], Awaitable[web.Response]]
    | Callable[[World, web.Request], AsyncGenerator[web.Response]]
)
FileHandler = Callable[[World, Path], Awaitable[None]]
Handlers = HttpHandler | FileHandler
