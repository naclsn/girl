#!/usr/bin/env python3
"""Usage: ./example.py [-h]"""

import logging
import sys

from girl import App
from girl import extra
from girl.events.file import Path
from girl.events.web import Request
from girl.store import BackendSqlite
from girl.store import Store
from girl.world import World

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(Store(BackendSqlite("ex.sqlite")))
app.file.event(Path(__file__).parent, "shell")(extra.shell)
extra.Webui(app, "localhost:8090", "/webui", basic_auth_passwd="coucou")


@app.web.event("localhost:8080", "GET", "/hi")
async def hi(world: World, req: Request):
    world.tag("hi")
    if name := req.rel_url.query.get("file"):
        world.tag(name)
        world.file(name).write_text("hello")
    return req.respond(text="hello")


@app.web.event("localhost:8080", "GET", "/proj")
async def proj(world: World, req: Request):
    # return req.respond(body=world.file("pyproject.toml").read_bytes())
    f = world.file("pyproject.toml")
    b = f.read_bytes()
    logger.debug(f"response is {len(b)} bytes")
    return req.respond(body=b)
    # return req.respond(file="pyproject.toml")  # content not in store ig


@app.file.event("./", "move.*")
async def moveme(world: World, file: Path):
    world.tag(f"src:{file}")
    logger.info("got move-me file")
    where = file.read_text().splitlines()[0].strip()
    assert where
    world.tag(f"dst:{where}")
    logger.info(f"mv {file} {where}")
    file.rename(where)


@app.cron.event((), (), (), ())  # every minute of every day
async def beat(_world: World):
    logger.info("alive")


if {"-h", "--help", "-n", "--dry-run"} & set(sys.argv[1:]):
    print(app.summary())
    exit("Starting with no argument will listen for these events.")
else:
    app.run()
