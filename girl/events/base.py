from abc import ABC
from abc import abstractmethod
from pathlib import PurePath
from types import TracebackType
from typing import Callable
from typing import TypeVar

_Fn_ = TypeVar("_Fn_", bound=Callable[..., object])
_Bind = tuple[str, int] | PurePath


def _reload_guard(
    id: str,
) -> Callable[[Callable[[_Fn_], _Fn_]], Callable[[_Fn_], _Fn_]]:
    """idea: only call function if not reloading or reloading this one"""
    if True or id is ladida:
        return lambda adder: adder
    return lambda adder: lambda fn: fn


class Base(ABC):
    """ """

    @abstractmethod
    def __init__(self): ...

    @abstractmethod
    def event(self, *a: ..., **ka: ...) -> Callable[[_Fn_], _Fn_]:
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
