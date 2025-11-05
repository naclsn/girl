from datetime import datetime

from pytest import mark
from pytest import raises

from girl.events.cron import _Schedule


def test_valid_args():
    with raises(ValueError, match="invalid minutes"):
        _Schedule([-1], (), (), ())
    with raises(ValueError, match="invalid months"):
        _Schedule((), (), (), [1, 17])
    with raises(ValueError, match="cannot mix"):
        _Schedule((), (), [42, "mon"], ())
    with raises(ValueError, match="cannot mix"):
        _Schedule((), (), ["mon", 42], ())
    with raises(ValueError, match="invalid day name"):
        _Schedule((), (), ["dabee"], ())
    with raises(ValueError, match="invalid month name"):
        _Schedule((), (), (), ["booda"])
    with raises(ValueError, match="must precede"):
        _Schedule(
            (), (), (), (), after=datetime(2000, 1, 1), before=datetime(1999, 1, 1)
        )


@mark.parametrize(
    ("_desc", "start", "sch", "seq"),
    [
        (
            "every minute of every day",
            datetime(2020, 1, 1, 0, 58),
            _Schedule(minutes=[], hours=[], days=[], months=[]),
            [
                datetime(2020, 1, 1, 0, 59),
                datetime(2020, 1, 1, 1, 0),
                datetime(2020, 1, 1, 1, 1),
                datetime(2020, 1, 1, 1, 2),
            ],
        ),
        (
            "all units overflow into new year",
            datetime(1999, 12, 31, 23, 58),
            _Schedule(minutes=[], hours=[], days=[], months=[]),
            [
                datetime(1999, 12, 31, 23, 59),
                datetime(2000, 1, 1, 0, 0),
                datetime(2000, 1, 1, 0, 1),
            ],
        ),
        (
            "5:05 every 29th, but year doesn't have a 02/29/",
            datetime(2025, 1, 1, 0, 0),
            _Schedule(minutes=5, hours=5, days=29, months=[]),
            [
                datetime(2025, 1, 29, 5, 5),
                datetime(2025, 3, 29, 5, 5),
                datetime(2025, 4, 29, 5, 5),
            ],
        ),
        (
            "every year on Mondays and Thursdays of July",
            datetime(2025, 7, 20, 2, 1),
            _Schedule(minutes=1, hours=2, days=["mOn", "tHUrS"], months="JuLY"),
            [
                datetime(2025, 7, 21, 2, 1),
                datetime(2025, 7, 24, 2, 1),
                datetime(2025, 7, 28, 2, 1),
                datetime(2025, 7, 31, 2, 1),
                datetime(2026, 7, 2, 2, 1),
                datetime(2026, 7, 6, 2, 1),
                datetime(2026, 7, 9, 2, 1),
                datetime(2026, 7, 13, 2, 1),
            ],
        ),
        (
            "with before/after params",
            datetime(2020, 2, 20, 2, 20),
            _Schedule(
                1, 2, 3, 4, after=datetime(2021, 1, 1), before=datetime(2023, 1, 1)
            ),
            [
                datetime(2021, 4, 3, 2, 1),
                datetime(2022, 4, 3, 2, 1),
                None,
            ],
        ),
        (
            "impossible date: before is before lol",
            datetime(2000, 1, 1, 0, 0),
            _Schedule((), (), 1, "nov", before=datetime(1990, 1, 1)),
            [None],
        ),
        (
            "impossible date: November 31th",
            datetime(2000, 1, 1, 0, 0),
            _Schedule(minutes=(), hours=(), days=31, months="nov"),
            [None],
        ),
    ],
    ids=lambda p: p if isinstance(p, str) else "",
)
def test_next_from(_desc: str, start: datetime, sch: _Schedule, seq: list[datetime]):
    curr = start
    ba = ((curr := sch.next_from(curr)) for _ in iter(int, 1))
    for expected, actual in zip(seq, ba):
        assert actual == expected, f"{actual!r} != {expected!r}"


@mark.parametrize(
    ("sch", "line"),
    [
        (_Schedule((), (), (), ()), "* * * *"),
        (_Schedule(range(0, 15), (), (), ()), "0-14 * * *"),
        (_Schedule((), (), (), ["oct", "nov", "dec", "jan"]), "* * * 1,10-12"),
        (_Schedule(0, 12, "mon", ()), "0 12 * * Mon"),
        (
            _Schedule(
                1, 2, 3, 4, after=datetime(1999, 1, 1), before=datetime(2000, 1, 1)
            ),
            "datetime.datetime(1999, 1, 1, 0, 0) <= 1 2 3 4 <= datetime.datetime(2000, 1, 1, 0, 0)",
        ),
    ],
    ids=lambda p: p if isinstance(p, str) else "",
)
def test_str_cron_line(sch: _Schedule, line: str):
    ye = str(sch)
    assert ye == line, f"{ye!r} != {line!r}"
