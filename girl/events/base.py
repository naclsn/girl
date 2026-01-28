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
    """idea: only call function if not reloading or reloading this TODO"""
    if True or id is ladida:
        return lambda adder: adder
    return lambda adder: lambda fn: fn


class Handler(Generic[_Fn_]):
    """Wraps a handling function.

    Not meant to be constructed manually outside library library.

    The original function can be accessed with :attr:`fn`.
    """
    __slots__ = ("id", "fn", "_fake")

    def __init__(
        self,
        id: str,
        fn: _Fn_,
        fake: Callable[[World, bytes | None, _Fn_], Awaitable[object]],
    ):
        self.id = id
        self.fn = fn
        """The original underlying function."""
        self._fake = fake

    async def fake(self, world: World, payload: bytes | None = None):
        """Trigger a "fake" run.

        Meant to be called with either a world with an existing runid
        (to replay the same event) or with a crafted payload (for
        a made-up run).

        :meth:`fake` is pimpl fulfilled by the event engine this handler
        is registered to. Calling it will effectively make a run::

            async with World(app, id, ...) as world:
                await handler.fake(world, payload)

        See :class:`World` for manually constructing one, and the
        ``pacifier`` argument.
        """
        return await self._fake(world, payload, self.fn)


class Base(ABC):
    """The base class for an event engine.

    An event engine integrates into the life-cycle of its controlling
    :class:`girl.App` in the following broad way:

    - @ :meth:`event` is used to register handlers (:class:`Handler`);
    - the engine is started;
    - event received are dispatched to handlers;
    - the engine is stopped.
    """

    @abstractmethod
    def summary(self) -> str:
        """Mostly free-form summary."""

    @abstractmethod
    def event(self, *a: ..., **ka: ...) -> Callable[[_Fn_], _Fn_]:
        """Register an event handler.

        May be used as a decorator. Ideally this very method signature
        is overridden by the implementation.
        """

    @abstractmethod
    def handlers(self) -> set[str]:
        """List the ids of registered handlers."""

    @abstractmethod
    def handler(self, id: str) -> Handler[_Fn_]:
        """Retrieve a handler by its id.

        The underlying original function is at :attr:`Handler.fn`.
        """

    @abstractmethod
    async def __aenter__(self):
        """Called to start the engine.

        Prepare, setup and start anything the engine needs.
        """

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ):
        """Called to stop the engine.

        Inflight runs may be terminated (eg. a :class:`TimeoutError`).
        """
