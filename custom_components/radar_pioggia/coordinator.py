"""Data update coordinator for Radar pioggia."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import logging
import math

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .analysis import (
    Frame,
    RadarResult,
    MAP_ZOOM_STEP,
    MAX_LEAD_MIN,
    MAX_SPEED_KMH,
    ZOOM,
    advect,
    analyse,
    build_basemap,
    build_field,
    crop_frame,
    decode_dpc_tile,
    decode_tile,
    frame_time,
    make_window,
    map_tiles,
    render_map,
    render_png,
    window_bounds,
)
from .api import BasemapClient, CannotConnect, DpcClient, RainViewerClient
from .const import (
    BASEMAPS,
    CONF_ALERT_KM,
    CONF_BASEMAP,
    CONF_HIDE_WEAK,
    CONF_RADIUS,
    DEFAULT_ALERT_KM,
    DEFAULT_BASEMAP,
    DEFAULT_RADIUS,
    DOMAIN,
    DPC_DELAY_MIN,
    DPC_STEP_MIN,
    FAST_POLL_S,
    FORECAST_MIN,
    FORECAST_STEP_MIN,
    FRAME_STEP_MIN,
    FRAMES,
    HISTORY_MIN,
    SCAN_INTERVAL_MIN,
    SOURCE_DPC,
    SOURCE_RAINVIEWER,
    WEAK_DBZ,
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
        self._dpc = DpcClient(session)
        self._rainviewer = RainViewerClient(session)
        self._rv_host = ""
        self._basemap_client = BasemapClient(session)
        self._basemap = None
        self._map_png: tuple[datetime, bytes] | None = None
        radius = entry.options.get(CONF_RADIUS, DEFAULT_RADIUS)
        self.window = make_window(entry.data[CONF_LATITUDE], entry.data[CONF_LONGITUDE], radius)
        self.bounds = window_bounds(self.window)
        # Frames are downloaded with a margin around the window: as far as the
        # fastest rain we track travels in the longest forecast. Rain still
        # outside the window then enters the map forecast and the arrival time.
        self._margin = math.ceil(MAX_SPEED_KMH * max(FORECAST_MIN, MAX_LEAD_MIN) / 60 / self.window.km_px)
        self._alert_km = entry.options.get(CONF_ALERT_KM, DEFAULT_ALERT_KM)
        # Weakest echo drawn on the map pictures (0 = all).
        self.min_dbz = WEAK_DBZ if entry.options.get(CONF_HIDE_WEAK, False) else 0
        # Base map of the picture and, unless the card sets its own, of the card.
        self.basemap_url, self.basemap_attribution = BASEMAPS.get(
            entry.options.get(CONF_BASEMAP), BASEMAPS[DEFAULT_BASEMAP]
        )
        self._area = self.window.grow(self._margin)
        # Decoded frames and their map images by "source:id", so each frame is
        # downloaded and drawn once.
        self._frames: dict[str, Frame] = {}
        self._pngs: dict[str, bytes] = {}
        self._last_key: str | None = None
        # Map frames for the card: the last HISTORY_MIN minutes, then the forecast.
        self.timeline: list[MapFrame] = []
        # Minutes between a DPC frame's time and its publication, learned from
        # the frames seen while checking every FAST_POLL_S seconds.
        self._dpc_delay = timedelta(minutes=DPC_DELAY_MIN)
        self._got_new = False

    async def _async_update_data(self) -> RadarResult:
        fast = self.update_interval is not None and self.update_interval <= timedelta(seconds=FAST_POLL_S)
        self.update_interval = timedelta(minutes=SCAN_INTERVAL_MIN)
        self._got_new = False
        try:
            result = await self._update_dpc()
        except CannotConnect as err:
            # A frame just announced may not be in the tile cache yet: keep the
            # recent DPC data and look again soon instead of switching source.
            if self._recent_dpc():
                _LOGGER.debug("Radar-DPC: fotogramma non ancora pronto (%s)", err)
                self.update_interval = timedelta(seconds=FAST_POLL_S)
                return self.data
            _LOGGER.debug("Radar-DPC non disponibile, uso RainViewer: %s", err)
        else:
            self._schedule_dpc(result.time, fast)
            return result
        try:
            return await self._update_rainviewer()
        except CannotConnect as err:
            raise UpdateFailed(f"Nessuna fonte radar disponibile: {err}") from err

    def _recent_dpc(self) -> bool:
        return (
            self.data is not None
            and self.data.source == SOURCE_DPC
            and dt_util.utcnow() - self.data.time < timedelta(minutes=20)
        )

    def _schedule_dpc(self, newest: datetime, fast: bool) -> None:
        """Check again just before the next frame is due, then every FAST_POLL_S.

        DPC publishes a frame every 5 minutes, some minutes after its nominal
        time, so a fixed 5-minute interval could see it up to 5 minutes late.
        """
        now = dt_util.utcnow()
        if self._got_new:
            # A new frame is out, so the delay is at most now - newest. Found
            # while checking often, that is the delay to within FAST_POLL_S;
            # found at the first check, DPC was quicker than learned.
            delay = now - newest
            if timedelta(minutes=1) <= delay <= timedelta(minutes=20) and (fast or delay < self._dpc_delay):
                self._dpc_delay = delay
        due = newest + timedelta(minutes=DPC_STEP_MIN) + self._dpc_delay - timedelta(seconds=FAST_POLL_S)
        if now - newest > timedelta(minutes=20):
            # DPC has stopped publishing: no need to keep asking often.
            wait = timedelta(minutes=SCAN_INTERVAL_MIN)
        else:
            wait = min(max(due - now, timedelta(seconds=FAST_POLL_S)), timedelta(minutes=SCAN_INTERVAL_MIN))
        self.update_interval = wait

    async def _update_dpc(self) -> RadarResult:
        last = await self._dpc.last_time()
        times = [last - timedelta(minutes=DPC_STEP_MIN * i) for i in reversed(range(HISTORY_MIN // DPC_STEP_MIN + 1))]
        # Analysis uses the newest frame and the ones 10 and 20 minutes before it.
        analysed = {last - timedelta(minutes=FRAME_STEP_MIN * i) for i in range(FRAMES)}
        return await self._update(
            SOURCE_DPC, [(f"dpc:{t:%Y%m%d%H%M}", t, t in analysed) for t in times]
        )

    async def _update_rainviewer(self) -> RadarResult:
        host, past = await self._rainviewer.frames()
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
        tiles_xy = self._area.tiles()
        if source == SOURCE_DPC:
            blobs = await asyncio.gather(*(self._dpc.tile(time, x, y) for x, y in tiles_xy))
            if all(b is None for b in blobs):
                raise CannotConnect(f"nessun tile per {time:%H:%M} UTC (punto fuori copertura?)")
            decoder = decode_dpc_tile
        else:
            path = key.removeprefix("rv:")
            blobs = await asyncio.gather(*(self._rainviewer.tile(self._rv_host, path, x, y) for x, y in tiles_xy))
            decoder = decode_tile
        tiles = dict(zip(tiles_xy, blobs))
        dbz, snow = await self.hass.async_add_executor_job(build_field, self._area, tiles, decoder)
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
        areas = [self._frames[k] for k, _, needed in wanted if needed]
        result = await self.hass.async_add_executor_job(analyse, areas, self.window, self._alert_km, self._margin)
        history = [(k, self._frames[k]) for k in keys if k in self._frames]
        self.timeline = await self.hass.async_add_executor_job(
            self._render_timeline, history, result.velocity
        )
        self._last_key = keys[-1]
        self._got_new = True
        return replace(result, source=source)

    @property
    def latest_frame(self) -> Frame | None:
        """The newest measured radar frame."""
        frame = self._frames.get(self._last_key) if self._last_key else None
        return crop_frame(frame, self._margin) if frame else None

    async def async_map_png(self, label_time: str) -> bytes | None:
        """Picture of the newest frame over the base map, for the image entity.

        The base map is downloaded only the first time a picture is asked for.
        """
        frame = self.latest_frame
        if frame is None:
            return None
        if self._map_png and self._map_png[0] == frame.time:
            return self._map_png[1]
        if self._basemap is None:
            keys = map_tiles(self.window)
            z = ZOOM + MAP_ZOOM_STEP
            try:
                blobs = await asyncio.gather(
                    *(self._basemap_client.tile(self.basemap_url, z, x, y) for x, y in keys)
                )
            except CannotConnect as err:
                _LOGGER.warning("Mappa di sfondo non disponibile: %s", err)
                blobs = [None] * len(keys)
            basemap, complete = await self.hass.async_add_executor_job(
                build_basemap, self.window, dict(zip(keys, blobs))
            )
            # Keep it only when complete, so a failed download is tried again.
            if complete:
                self._basemap = basemap
        else:
            basemap = self._basemap
        source = self.data.source if self.data else ""
        label = " · ".join(p for p in (label_time, source, self.basemap_attribution) if p)
        png = await self.hass.async_add_executor_job(render_map, basemap, frame.dbz, frame.snow, label, self.min_dbz)
        self._map_png = (frame.time, png)
        return png

    def _render_timeline(self, history: list[tuple[str, Frame]], velocity) -> list[MapFrame]:
        """Map images: past frames (cached) and the newest one moved forward."""
        out = []
        for key, frame in history:
            if key not in self._pngs:
                inner = crop_frame(frame, self._margin)
                self._pngs[key] = render_png(inner.dbz, inner.snow, self.min_dbz)
            out.append(MapFrame(frame.time, False, self._pngs[key]))
        if velocity is not None and history:
            newest = history[-1][1]
            for minutes in range(FORECAST_STEP_MIN, FORECAST_MIN + 1, FORECAST_STEP_MIN):
                moved = Frame(newest.time, *advect(newest.dbz, newest.snow, velocity, minutes))
                inner = crop_frame(moved, self._margin)
                out.append(MapFrame(newest.time + timedelta(minutes=minutes), True, render_png(inner.dbz, inner.snow, self.min_dbz)))
        return out


@dataclass(frozen=True)
class MapFrame:
    """One image of the radar map card."""

    time: datetime
    forecast: bool
    png: bytes
