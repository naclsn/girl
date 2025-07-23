import asyncio

from ..world import Path
from ..world import World


async def shell(_world: World, file: Path):
    r, w = await asyncio.open_unix_connection(file)
    file.unlink()
    async for line in r:
        w.write("".join(reversed(list(line.decode().strip()))).encode() + b"\n")
