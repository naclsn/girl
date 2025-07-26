"""A collection of managment procs."""

from inspect import getfullargspec
from logging import getLogger
from typing import Callable
from typing import TypeVar

_logger = getLogger(__name__)

_SIMPLE_OK_TY = {str, int, float, list[str], list[int], list[float]}


_Fn_ = TypeVar("_Fn_", bound=Callable[..., object])


def _proc(rfn: _Fn_) -> _Fn_:
    spec = getfullargspec(rfn)
    assert not spec.args, f"{rfn} is supposed to only have kwargs"
    assert spec.annotations.keys() == set(spec.kwonlyargs), f"{rfn} missing hints"
    assert set(spec.annotations.values()) < _SIMPLE_OK_TY, f"{rfn} uses complex types"
    setattr(rfn, "_rpc_params", spec.annotations)
    return rfn


@_proc
async def a(*, a: str):
    return "coucou " + a
