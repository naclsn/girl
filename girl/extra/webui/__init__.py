""""""

from base64 import b64decode
from logging import getLogger
from pathlib import PurePath

from aiohttp import web

from ...app import App
from ...events.web import Request
from ...world import World
from .. import procs

_logger = getLogger(__name__)

_STATIC_ROOT = PurePath(__file__).parent / "static"


async def notif(world: World, req: Request):
    res = web.WebSocketResponse()
    assert req._req, "not a real request? (crafted or replayed?)"
    await res.prepare(req._req)
    _logger.info("websocket listening for submissions")
    hook = world.app.hook.submit(
        lambda id, runid, ts, tags: res.send_json(
            {"id": id, "runid": runid, "ts": ts, "tags": list(tags)}
        )
    )
    try:
        await res.receive()  # XXX: or asyncio.sleep loop? maybe listen for filters?
    except:
        await res.close()
        raise
    finally:
        world.app.hook.submit.remove(hook)
    return res


class Webui:
    """ """

    def __init__(
        self,
        app: App,
        bind: str | PurePath,
        subpath: str,
        /,
        *,
        basic_auth_passwd: str | None = None,
        # by default, queries go [now-that .. now]; this includes:
        #  - the initial query at page load
        #  - force searches with no given min_ts
        query_default_backrange: float = 60 * 60 * 24,
        # how many notifs will be at most put in the feed's list
        notif_limit: int = 500,
        # renames title
        app_name: str = "app",
        favicon_path: str | PurePath | None = None,
    ):
        self._subpath = subpath
        self._basic_auth_passwd = basic_auth_passwd
        self._query_default_backrange = query_default_backrange
        self._notif_limit = notif_limit
        self._app_name = app_name
        self._favicon_path = favicon_path and str(favicon_path)

        app.web.event(bind, "GET", f"{subpath}/{{file:(?:[^/]*)?}}")(self._serve)
        app.web.event(bind, "GET", f"{subpath}/-/sitelocal.json")(self._sitelocal)
        app.web.event(bind, "GET", f"{subpath}/-/api/handlers")(self._api_handlers)
        app.web.event(bind, "GET", f"{subpath}/-/api/events")(self._api_events)
        app.web.event(bind, "GET", f"{subpath}/-/api/data")(self._api_data)
        app.web.event(bind, "GET", f"{subpath}/-/api/tags")(self._api_tags)
        app.web.event(bind, "GET", f"{subpath}/-/notif")(notif)

    async def _serve(self, _world: World, req: Request):
        file = req.match_info.get("file") or "index.html"
        _logger.info(f"get: {file}")
        if "favicon.ico" == file and self._favicon_path != None:
            file = self._favicon_path
            _logger.info(f"now: {file}")
        return req.respond(file=_STATIC_ROOT / file)

    async def _sitelocal(self, _world: World, req: Request):
        return req.respond(
            json={
                "subpath": self._subpath,
                "basic_auth_passwd": self._basic_auth_passwd is None,
                "query_default_backrange": self._query_default_backrange,
                "notif_limit": self._notif_limit,
                "app_name": self._app_name,
                "favicon_path": self._favicon_path,
            }
        )

    async def _api_handlers(self, world: World, req: Request):
        filter = req.rel_url.query.get("filter", "all:*")
        return req.respond(json=await procs.lshandlers(filter, app=world.app))

    async def _api_events(self, world: World, req: Request):
        filter = req.rel_url.query.get("filter", "all:*")
        min_ts = req.rel_url.query.get("min_ts", "0")
        max_ts = req.rel_url.query.get("max_ts", "10e10")  # (consistent with lsevents)
        try:
            min_ts = float(min_ts)
        except:
            pass
        try:
            max_ts = float(max_ts)
        except:
            pass
        any_tag = req.rel_url.query.getall("any_tag", None)
        l = await procs.lsevents(filter, min_ts, max_ts, any_tag, app=world.app)
        return req.respond(
            json={
                id: [
                    {"ts": run.ts, "runid": run.runid, "tags": sorted(run.tags)}
                    for run in runs
                ]
                for id, runs in l.items()
            }
        )

    async def _api_data(self, world: World, req: Request):
        if self._basic_auth_passwd:
            auth = req.header("Authorization")
            if not auth or not "basic " == auth[:6].lower():
                return req.respond(
                    headers={"WWW-Authenticate": 'Basic realm="data"'},
                    status=401,
                )
            _, _, passwd = b64decode(auth[6:]).decode().partition(":")
            if passwd != self._basic_auth_passwd:
                return req.respond(status=403)

        runid = req.rel_url.query["runid"]
        run = await procs.lsdata(runid, app=world.app)
        return req.respond(
            json={
                "ts": run.ts,
                "runid": run.runid,
                "tags": sorted(run.tags),
                # 1. bytes cannot be json serialized: decode+backslash non utf8,
                # 2. python dict keep order but receiving end may not: use a list
                "data": [
                    {
                        "key": key,
                        "ts": ts,
                        # this will be transmitting secrets! there could be a way
                        # to hook in and filter data to blank out anything that should
                        "data": data.decode(errors="backslashreplace"),
                    }
                    for key, (ts, data) in run.data.items()
                ],
            }
        )

    async def _api_tags(self, world: World, req: Request):
        return req.respond(json=sorted(await procs.lstags(app=world.app)))
