"""A collection of managment procs."""

import asyncio
from code import InteractiveConsole
from collections.abc import Awaitable
from functools import wraps
from inspect import getfullargspec
from logging import getLogger
from typing import Callable
from typing import TypeVar

_logger = getLogger(__name__)

_TY_TL_TABLE: dict[type, Callable[[str], object]] = {
    str: str,
    int: int,
    float: float,
    list[str]: lambda s: s.split(","),
    list[int]: lambda s: map(int, s.split(",")),
    list[float]: lambda s: map(float, s.split(",")),
}
_Afn_ = TypeVar("_Afn_", bound=Callable[..., Awaitable[object]])
_T_ = TypeVar("_T_")


def _proc(rfn: _Afn_) -> _Afn_:
    spec = getfullargspec(rfn)
    # assert spec.annotations.keys() == set(spec.args), f"{rfn} missing hints"
    # assert set(spec.annotations.values()) < _TY_TL_TABLE.keys(), f"{rfn} complex types"
    setattr(rfn, "_rpc_params", spec.annotations)

    @wraps(rfn)
    async def wfn(*a: ..., io: Interact):
        return await (rfn(*a, io=io) if "io" in spec.annotations else rfn(*a))

    return wfn


class Interact:
    """ """

    def __init__(
        self,
        abreadline: Callable[[], Awaitable[bytes]],
        abwriteflush: Callable[[bytes], Awaitable[None]] | None,
    ):
        self.abreadline = abreadline
        self.abwriteflush = abwriteflush
        self._buf = bytearray()
        self._loop = asyncio.get_event_loop()

    async def aflush(self):
        if self.abwriteflush:
            await self.abwriteflush(bytes(self._buf))
        self._buf.clear()

    def readline(self):
        fut = asyncio.run_coroutine_threadsafe(self.abreadline(), self._loop)
        return fut.result().decode()

    def flush(self):
        asyncio.run_coroutine_threadsafe(self.aflush(), self._loop).result()

    def write(self, data: str):
        self._buf.extend(data.encode())


@_proc
async def a(a: str):
    return "coucou " + a


@_proc
async def interact(*, io: Interact):
    class Interp(InteractiveConsole):
        def write(self, data: str):
            io.write(data)

        def raw_input(self, prompt: str = ""):
            if prompt:
                io.write(prompt)
            io.flush()
            return io.readline()

    # TODO: displayhook situation

    try:
        await asyncio.to_thread(Interp({"io": io}).interact, "*interactive*")
    except SystemExit:
        pass


@_proc
async def cmd(*, io: Interact):
    from cmd import Cmd

    class Da(Cmd):
        use_rawinput = False

        def do_echo(self, args: str):
            self.stdout.write(f"{' '.join(args.split())}\n")

        def do_exit(self, _: str):
            return True

        do_EOF = do_exit

    await asyncio.to_thread(Da(stdin=io, stdout=io).cmdloop, "*cmd*")


@_proc
async def b(*, io: Interact):
    import threading

    def inner():
        print("inside", threading.current_thread())
        print("reasding")
        l = io.readline()
        print("read, writin")
        io.write(f"bidoof {l}")
        print("wrote, fluhsin")
        io.flush()
        print("dslndsn")

    print("outside", threading.current_thread())
    await asyncio.to_thread(inner)
