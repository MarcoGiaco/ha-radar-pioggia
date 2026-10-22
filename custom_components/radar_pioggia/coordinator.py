"""Data update coordinator for Radar pioggia."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .analysis import (
    Frame,
    RadarResult,
    advect,
    analyse,
    build_field,
    decode_dpc_tile,
    decode_tile,
    frame_time,
    make_window,
    render_png,
    window_bounds,
)
from .api import CannotConnect, DpcClient, RainViewerClient
from .const import (
    CONF_RADIUS,
    DEFAULT_RADIUS,
    DOMAIN,
    DPC_STEP_MIN,
    FORECAST_MIN,
    FORECAST_STEP_MIN,
    FRAME_STEP_MIN,
    FRAMES,
    HISTORY_MIN,
    SCAN_INTERVAL_MIN,
    SOURCE_DPC,
    SOURCE_RAINVIEWER,
)

_LOGGER = logging.getLogger(__name__)

type RadarConfigEntry = ConfigEntry[RadarCoordinator]


class RadarCoordinator(DataUpdateCoordinator[RadarResult]):
    """Download new radar frames and analyse them for the configured point.

    Radar-DPC is used first (Italy, every 5 minutes, raw dBZ). If it cannot be
    reached or does not cover the point, RainViewer is used instead.
    """

    config_entry: RadarConfigEntry

    def __init__(self, hass: HomeAssistant, entry: RadarConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(minutes=SCAN_INTERVAL_MIN),
        )
        session = async_get_clientsession(hass)
        self.dpc = DpcClient(session)
        self.rainviewer = RainViewerClient(session)
        radius = entry.options.get(CONF_RADIUS, DEFAULT_RADIUS)
        self.window = make_window(entry.data[CONF_LATITUDE], entry.data[CONF_LONGITUDE], radius)
        self.bounds = window_bounds(self.window)
        # Decoded frames and their map images by "source:id", so each frame is
        # downloaded and drawn once.
        self._frames: dict[str, Frame] = {}
        self._pngs: dict[str, bytes] = {}
        self._last_key: str | None = None
        # Map frames for the card: the last HISTORY_MIN minutes, then the forecast.
        self.timeline: list[MapFrame] = []

    async def _async_update_data(self) -> RadarResult:
        try:
            return await self._update_dpc()
        except CannotConnect as err:
            _LOGGER.debug("Radar-DPC non disponibile, uso RainViewer: %s", err)
        try:
            return await self._update_rainviewer()
        except CannotConnect as err:
            raise UpdateFailed(f"Nessuna fonte radar disponibile: {err}") from err

    async def _update_dpc(self) -> RadarResult:
        last = await self.dpc.last_time()
        times = [last - timedelta(minutes=DPC_STEP_MIN * i) for i in reversed(range(HISTORY_MIN // DPC_STEP_MIN + 1))]
        # Analysis uses the newest frame and the ones 10 and 20 minutes before it.
        analysed = {last - timedelta(minutes=FRAME_STEP_MIN * i) for i in range(FRAMES)}
        return await self._update(
            SOURCE_DPC, [(f"dpc:{t:%Y%m%d%H%M}", t, t in analysed) for t in times]
        )

    async def _update_rainviewer(self) -> RadarResult:
        host, past = await self.rainviewer.frames()
        if not past:
            raise CannotConnect("RainViewer non ha fotogrammi radar")
        self._rv_host = host
        newest = frame_time(past[-1]["time"])
        # RainViewer frames are 10 minutes apart, like FRAME_STEP_MIN.
        wanted = [
            (f"rv:{item['path']}", frame_time(item["time"]), i >= len(past) - FRAMES)
            for i, item in enumerate(past)
            if newest - frame_time(item["time"]) <= timedelta(minutes=HISTORY_MIN)
        ]
        return await self._update(SOURCE_RAINVIEWER, wanted)

    async def _download(self, source: str, key: str, time: datetime) -> Frame:
        tiles_xy = self.window.tiles()
        if source == SOURCE_DPC:
            blobs = await asyncio.gather(*(self.dpc.tile(time, x, y) for x, y in tiles_xy))
            if all(b is None for b in blobs):
                raise CannotConnect(f"nessun tile per {time:%H:%M} UTC (punto fuori copertura?)")
            decoder = decode_dpc_tile
        else:
            path = key.removeprefix("rv:")
            blobs = await asyncio.gather(*(self.rainviewer.tile(self._rv_host, path, x, y) for x, y in tiles_xy))
            decoder = decode_tile
        tiles = dict(zip(tiles_xy, blobs))
        dbz, snow = await self.hass.async_add_executor_job(build_field, self.window, tiles, decoder)
        return Frame(time, dbz, snow)

    async def _update(self, source: str, wanted: list[tuple[str, datetime, bool]]) -> RadarResult:
        keys = [key for key, _, _ in wanted]
        if keys[-1] == self._last_key and self.data is not None:
            return self.data

        for key, time, needed in wanted:
            if key in self._frames:
                continue
            try:
                self._frames[key] = await self._download(source, key, time)
            except CannotConnect:
                # A missing old frame only leaves a gap in the map history.
                if needed:
                    raise
                _LOGGER.debug("Fotogramma %s non disponibile, saltato", key)

        self._frames = {k: f for k, f in self._frames.items() if k in keys}
        self._pngs = {k: p for k, p in self._pngs.items() if k in keys}
        frames = [self._frames[k] for k, _, needed in wanted if needed]
        result = await self.hass.async_add_executor_job(analyse, frames, self.window)
        history = [(k, self._frames[k]) for k in keys if k in self._frames]
        self.timeline = await self.hass.async_add_executor_job(
            self._render_timeline, history, result.velocity
        )
        self._last_key = keys[-1]
        return replace(result, source=source)

    def _render_timeline(self, history: list[tuple[str, Frame]], velocity) -> list[MapFrame]:
        """Map images: past frames (cached) and the newest one moved forward."""
        out = []
        for key, frame in history:
            if key not in self._pngs:
                self._pngs[key] = render_png(frame.dbz, frame.snow)
            out.append(MapFrame(frame.time, False, self._pngs[key]))
        if velocity is not None and history:
            newest = history[-1][1]
            for minutes in range(FORECAST_STEP_MIN, FORECAST_MIN + 1, FORECAST_STEP_MIN):
                dbz, snow = advect(newest.dbz, newest.snow, velocity, minutes)
                out.append(MapFrame(newest.time + timedelta(minutes=minutes), True, render_png(dbz, snow)))
        return out


@dataclass(frozen=True)
class MapFrame:
    """One image of the radar map card."""

    time: datetime
    forecast: bool
    png: bytes
