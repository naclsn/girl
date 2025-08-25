#!/usr/bin/env python3

import logging

from girl import App
from girl import extra
from girl.events.file import Path
from girl.events.web import Request
from girl.store import BackendMemory
from girl.world import World

logging.basicConfig(level=logging.NOTSET)
logger = logging.getLogger(__name__)

app = App(BackendMemory())
app.file.event(Path(__file__).parent, "shell")(extra.shell)


@app.web.event("localhost:8080", "GET", "/hi")
async def hi(world: World, req: Request):
    if name := req.rel_url.query.get("file"):
        world.file(name).write_text("hello")
    return req.respond(text="hello")


@app.web.event("localhost:8080", "GET", "/proj")
async def proj(world: World, req: Request):
    # return req.respond(body=world.file("pyproject.toml").read_bytes())
    f = world.file("pyproject.toml")
    b = f.read_bytes()
    logger.debug(f"response is {len(b)} bytes")
    return req.respond(body=b)


@app.cron.event()  # every minute of every day
async def beat(_world: World):
    logger.info("alive")


app.run()
