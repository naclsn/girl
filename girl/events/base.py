from abc import ABC
from abc import abstractmethod
from collections.abc import Awaitable
from types import TracebackType
from typing import Callable
from typing import Generic
from typing import TypeVar

from ..world import World

_Fn_ = TypeVar("_Fn_", bound=Callable[..., object])


def _reload_guard(
    id: str,
) -> Callable[[Callable[[_Fn_], _Fn_]], Callable[[_Fn_], _Fn_]]:
    """idea: only call function if not reloading or reloading this one"""
    if True or id is ladida:
        return lambda adder: adder
    return lambda adder: lambda fn: fn


class Handler(Generic[_Fn_]):
    __slots__ = ("id", "fn", "_fake")

    def __init__(
        self,
        id: str,
        fn: _Fn_,
        fake: Callable[[World, bytes, _Fn_], Awaitable[object]],
    ):
        self.id = id
        self.fn = fn
        self._fake = fake

    async def fake(self, world: World, payload: bytes):
        return await self._fake(world, payload, self.fn)


class Base(ABC):
    """ """

    @abstractmethod
    def event(self, *a: ..., **ka: ...) -> Callable[[_Fn_], _Fn_]:
        """ """

    @abstractmethod
    def handlers(self) -> set[str]:
        """ """

    @abstractmethod
    def handler(self, id: str) -> Handler[_Fn_]:
        """ """

    @abstractmethod
    async def __aenter__(self):
        """ """

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        """ """
