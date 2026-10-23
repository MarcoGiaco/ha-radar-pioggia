"""HTTP clients for the radar sources: Radar-DPC (Italy) and RainViewer (worldwide)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .analysis import TILE, ZOOM
from .const import BASEMAP_URL, DPC_API_URL, DPC_TILE_URL, MAPS_URL, USER_AGENT

TIMEOUT = aiohttp.ClientTimeout(total=20)
# RainViewer: Universal Blue colors (the only scheme the free API serves), no smoothing, snow shown apart.
COLOR = 2
OPTIONS = "0_1"
# Radar-DPC product: Vertical Maximum Intensity, dBZ, every 5 minutes.
DPC_PRODUCT = "VMI"


class CannotConnect(Exception):
    """The radar source could not be reached or answered with an error."""


class _Client:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._headers = {"User-Agent": USER_AGENT}

    async def _get(self, url: str, missing_ok: bool = False) -> aiohttp.ClientResponse | None:
        try:
            resp = await self._session.get(url, headers=self._headers, timeout=TIMEOUT)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise CannotConnect(str(err)) from err
        # The DPC tile cache answers 403/404 for tiles it has no data for.
        if missing_ok and resp.status in (403, 404):
            return None
        if resp.status != 200:
            raise CannotConnect(f"HTTP {resp.status} for {url}")
        return resp


class DpcClient(_Client):
    """Radar-DPC, the Italian national radar mosaic (Dipartimento della Protezione Civile)."""

    async def last_time(self) -> datetime:
        """Time of the newest VMI product."""
        resp = await self._get(f"{DPC_API_URL}/findLastProductByType?type={DPC_PRODUCT}&lang=it")
        try:
            data = await resp.json(content_type=None)
            ms = data["lastProducts"][0]["time"]
        except (ValueError, KeyError, IndexError, TypeError) as err:
            raise CannotConnect("Invalid DPC product list") from err
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

    async def tile(self, time: datetime, x: int, y: int) -> bytes | None:
        """One zoom-7 VMI tile as WebP bytes, None if the cache has no data for it."""
        url = DPC_TILE_URL.format(
            product=DPC_PRODUCT,
            date=time.strftime("%Y/%m/%d"),
            hhmm=time.strftime("%H%M"),
            z=ZOOM, x=x, y=y,
            name=DPC_PRODUCT.lower(),
        )
        resp = await self._get(url, missing_ok=True)
        return None if resp is None else await resp.read()


class RainViewerClient(_Client):
    """RainViewer public API, used when Radar-DPC is not available."""

    async def frames(self) -> tuple[str, list[dict[str, Any]]]:
        """Tile host and the past radar frames, oldest first."""
        resp = await self._get(MAPS_URL)
        try:
            data = await resp.json(content_type=None)
            return data["host"], data["radar"]["past"]
        except (ValueError, KeyError, TypeError) as err:
            raise CannotConnect("Invalid frame list") from err

    async def tile(self, host: str, path: str, x: int, y: int) -> bytes:
        """One zoom-7 radar tile as PNG bytes."""
        resp = await self._get(f"{host}{path}/{TILE}/{ZOOM}/{x}/{y}/{COLOR}/{OPTIONS}.png")
        return await resp.read()


class BasemapClient(_Client):
    """OpenStreetMap tiles for the map picture, downloaded once per point."""

    async def tile(self, z: int, x: int, y: int) -> bytes | None:
        resp = await self._get(BASEMAP_URL.format(z=z, x=x, y=y), missing_ok=True)
        return None if resp is None else await resp.read()
