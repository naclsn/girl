from pathlib import Path
from sqlite3 import Connection

import aiosqlite

from .base import Base
from .base import LoadedRun


class BackendSqlite(Base):
    """ """

    def __init__(self, path_or_conn: str | Path | Connection | aiosqlite.Connection):
        if isinstance(path_or_conn, Connection):
            self._path = None
            self._conn = aiosqlite.Connection(lambda: path_or_conn, 64)
        elif isinstance(path_or_conn, aiosqlite.Connection):
            self._path = None
            self._conn = path_or_conn
        else:
            self._path = Path(path_or_conn)

    async def storerun(self, id: str, runid: str, run: LoadedRun):
        """"""
        ts, data = run
        await self._conn.execute(
            r"INSERT INTO event_runs VALUES (?, ?, ?)",
            (id, runid, ts),
        )
        await self._conn.executemany(
            r"INSERT INTO run_data VALUES (?, ?, ?, ?)",
            [(runid, key, ts, data) for key, (ts, data) in data.items()],
        )
        await self._conn.commit()

    async def loadrun(self, id: str, runid: str):
        """"""
        c = await self._conn.execute(
            r"SELECT ts FROM event_runs WHERE ? = id AND ? = runid",
            (id, runid),
        )
        if (one := await c.fetchone()) is None:
            raise LookupError(f"no run for {id!r} {runid!r}")
        ts = one[0]
        all = await self._conn.execute_fetchall(
            r"SELECT key, ts, data FROM event_runs WHERE ? = id AND ? = runid",
            (id, runid),
        )
        data = {key: (ts, data) for key, ts, data in all}
        return (ts, data)

    async def listruns(self, id: str):
        """"""
        all = await self._conn.execute_fetchall(
            r"SELECT ts, runid FROM event_runs WHERE ? = id ORDER BY ts",
            (id,),
        )
        return list(map(tuple, all))

    async def status(self):
        c = await self._conn.execute(
            r"""
 SELECT (page_count - freelist_count) * page_size as size
 FROM pragma_page_count(), pragma_freelist_count(), pragma_page_size()
 """,
            (),
        )
        return f"{int((await c.fetchone())[0]):_} B"

    async def __aenter__(self):
        self._conn = await (aiosqlite.connect(self._path) if self._path else self._conn)
        await self._conn.executescript(
            r"""
 CREATE TABLE IF NOT EXISTS event_runs (
    id    TEXT             NOT NULL, -- eg. "localhost:8080 GET /hi"
    runid TEXT PRIMARY KEY NOT NULL, -- eg. "some-banana"
    ts    REAL             NOT NULL)
 STRICT, WITHOUT ROWID;
 CREATE TABLE IF NOT EXISTS run_data (
    runid TEXT             NOT NULL, -- eg. "some-banana"
    key   TEXT             NOT NULL, -- eg. "*request-body*" or "/some/file"
    ts    REAL             NOT NULL,
    data  BLOB             NOT NULL,
    FOREIGN KEY(runid) REFERENCES event_runs(runid),
    PRIMARY KEY(runid, key))
 STRICT, WITHOUT ROWID;
 """,
        )

    async def __aexit__(self, *_):
        await self._conn.commit()
        await self._conn.close()
