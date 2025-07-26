#!/usr/bin/env python3

import asyncio
import logging

from aiohttp.web import Request
from aiohttp.web import Response

from girl import App
from girl import extra
from girl.world import Path
from girl.world import World

logging.basicConfig(level=logging.NOTSET)
logger = logging.getLogger(__name__)

app = App()

app.file.event(Path(__file__).parent, "shell")(extra.shell)
app.web.event("localhost:8091", "GET", "/shell")(extra.shell)


@app.web.event("localhost:8080", "GET", "/hi")
async def hi(_world: World, _req: Request):
    return Response(text="hello")


@app.web.event("localhost:8080", "GET", "/wait")
async def wait(_world: World, req: Request):
    txt = req.query["for"]
    match txt[-1:]:
        case "h":
            delay = 3600 * float(txt[:-1])
        case "m":
            delay = 60 * float(txt[:-1])
        case "s":
            delay = float(txt[:-1])
        case _:
            delay = float(txt or 1)
    await asyncio.sleep(delay)
    return Response(text=f"{delay}s")


@app.file.event("./", "move.me")
async def moveme(_world: World, file: Path):
    logger.info("got move.me file")
    where = file.read_text().strip()
    assert where
    logger.info(f"mv {file} {where}")
    file.rename(where)


@app.file.event("./", "ohce")
async def ohce(_world: World, file: Path):
    r, w = await asyncio.open_unix_connection(file)
    file.unlink()
    async for line in r:
        w.write("".join(reversed(list(line.decode().strip()))).encode() + b"\n")


@app.file.event("./", "*")
async def anyfile(_world: World, file: Path):
    logger.info("hay! %s %s %s", file, type(file), repr(file))


app.run()


"""
if "__main__" == __name__:
    parse = ArgumentParser()
    parse.add_argument("command", choices={"run", "shell"})
    args = parse.parse_args()

    match args.command:
        case "run":
            app.run()
        case "shell":
            patapatate
            # that, or, something that feels cool is to just have, like, normal events?
            # app.event_web(...)(app.remoteadmin) # (but other name) index.html + rest api
            # app.event_file(...)(app.remoteadmin) # a socket or pipe or idk idcare
        case _:
            pass
"""
