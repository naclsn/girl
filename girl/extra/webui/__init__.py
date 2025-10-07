""""""

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


async def api(world: World, req: Request):
    # XXX(wip): something to work with
    world.tag(req.match_info["thing"])

    match req.match_info["thing"]:
        case "handlers":
            filter = req.rel_url.query.get("filter", "all:*")
            return req.respond(json=await procs.lshandlers(filter, app=world.app))

        case "events":
            filter = req.rel_url.query.get("filter", "all:*")
            min_ts = req.rel_url.query.get("min_ts", "0")
            max_ts = req.rel_url.query.get("max_ts", "10e10")
            try:
                min_ts = float(min_ts)
            except:
                pass
            try:
                max_ts = float(max_ts)
            except:
                pass
            any_tag = req.rel_url.query.getall("any_tag", None)
            found = await procs.lsevents(filter, min_ts, max_ts, any_tag, app=world.app)
            return req.respond(
                json={
                    id: [
                        {"ts": run.ts, "runid": run.runid, "tags": sorted(run.tags)}
                        for run in runs
                    ]
                    for id, runs in found.items()
                }
            )

        case "data":
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
                            # TODO: this will be transmitting secrets! there should be a way
                            # to hook in and filter data to blank out anything that needs to be
                            "data": data.decode(errors="backslashreplace"),
                        }
                        for key, (ts, data) in run.data.items()
                    ],
                }
            )

        case _:
            return req.respond(status=404)


async def _serve(world: World, req: Request):
    # XXX(wip): something to work with
    world.tag(req.match_info.get("file") or "index.html")
    return req.respond(file=_STATIC_ROOT / (req.match_info.get("file") or "index.html"))


def setup(app: App, bind: str | PurePath, subpath: str):
    app.web.event(bind, "GET", f"{subpath}/-/notif")(notif)
    app.web.event(bind, "GET", f"{subpath}/-/api/{{thing}}")(api)
    app.web.event(bind, "GET", f"{subpath}/{{file:(?:[^/]*)?}}")(_serve)
