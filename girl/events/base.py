from abc import ABC
from abc import abstractmethod
from types import TracebackType
from typing import Callable
from typing import Generic
from typing import TypeVar

_Fn_ = TypeVar("_Fn_", bound=Callable[..., object])


def _reload_guard(
    id: str,
) -> Callable[[Callable[[_Fn_], _Fn_]], Callable[[_Fn_], _Fn_]]:
    """idea: only call function if not reloading or reloading this one"""
    if True or id is ladida:
        return lambda adder: adder
    return lambda adder: lambda fn: fn


class Handler(Generic[_Fn_]):
    __slots__ = ("id", "fn")

    def __init__(self, id: str, fn: _Fn_):
        self.id = id
        self.fn = fn


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
