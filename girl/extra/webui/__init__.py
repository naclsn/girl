""""""

from logging import getLogger
from pathlib import PurePath

from aiohttp import web

from ...events.web import Request
from ...app import App
from ...world import World

_logger = getLogger(__name__)

_STATIC_ROOT = PurePath(__file__) / "static"


async def notif(world: World, req: Request):
    res = web.WebSocketResponse()
    assert req._req, "not a real request? (crafted or replayed?)"
    await res.prepare(req._req)
    _logger.info("websocket listening for submissions")
    hook = world.app.hook.submit(
        lambda id, runid, ts: res.send_json({"id": id, "runid": runid, "ts": ts})
    )
    try:
        await res.receive()
    except:
        await res.close()
        raise
    finally:
        world.app.hook.submit.remove(hook)
    return res


async def _serve(_world: World, req: Request):
    return req.respond(file=_STATIC_ROOT / (req.match_info.get("file") or "index.html"))


def setup(app: App, bind: str | PurePath, subpath: str):
    app.web.event(bind, "GET", f"{subpath}/-/notif")(notif)
    # app.web.event(bind, "GET", f"{subpath}/-/shell")(extra.shell)
    app.web.event(bind, "GET", f"{subpath}/{{file}}")(_serve)
