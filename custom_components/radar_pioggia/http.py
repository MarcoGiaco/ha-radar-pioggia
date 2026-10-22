"""HTTP endpoints for the radar map card: frame list and frame images."""

from __future__ import annotations

from http import HTTPStatus

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import ATTRIBUTION, DOMAIN


def _coordinator(hass: HomeAssistant, entry_id: str):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or not hasattr(entry, "runtime_data"):
        return None
    return entry.runtime_data


class RadarFramesView(HomeAssistantView):
    """Frames of one point, found from any of its entities."""

    url = "/api/radar_pioggia/frames/{entity_id}"
    name = "api:radar_pioggia:frames"

    async def get(self, request: web.Request, entity_id: str) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        reg = er.async_get(hass).async_get(entity_id)
        coordinator = reg and reg.config_entry_id and _coordinator(hass, reg.config_entry_id)
        if not coordinator:
            return self.json_message("Entità radar_pioggia non trovata", HTTPStatus.NOT_FOUND)
        data = coordinator.data
        source = data.source if data else None
        timeline = coordinator.timeline
        newest = int(timeline[-1].time.timestamp()) if timeline else 0
        return self.json(
            {
                "bounds": coordinator.bounds,
                "center": [
                    coordinator.config_entry.data["latitude"],
                    coordinator.config_entry.data["longitude"],
                ],
                "source": source,
                "attribution": ATTRIBUTION,
                "frames": [
                    {
                        "time": f.time.isoformat(),
                        "forecast": f.forecast,
                        "url": _image_url(reg.config_entry_id, f, source, newest),
                    }
                    for f in timeline
                ],
            }
        )


def _image_url(entry_id: str, frame, source: str | None, newest: int) -> str:
    """Address of one frame image.

    It depends only on what the image shows, so the browser keeps measured
    frames across updates and fetches again only the forecast, which is
    recomputed from every new radar image.
    """
    url = f"/api/radar_pioggia/image/{entry_id}/{int(frame.time.timestamp())}?s={source}"
    if frame.forecast:
        url += f"&n={newest}"
    return url


class RadarImageView(HomeAssistantView):
    """One frame of the map as a transparent PNG."""

    url = "/api/radar_pioggia/image/{entry_id}/{stamp}"
    name = "api:radar_pioggia:image"

    async def get(self, request: web.Request, entry_id: str, stamp: str) -> web.Response:
        coordinator = _coordinator(request.app["hass"], entry_id)
        if coordinator is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        frame = next(
            (f for f in coordinator.timeline if str(int(f.time.timestamp())) == stamp),
            None,
        )
        # The list moved on since the card read it: let the card read it again.
        if frame is None:
            return web.Response(status=HTTPStatus.CONFLICT)
        return web.Response(
            body=frame.png,
            content_type="image/png",
            headers={"Cache-Control": "private, max-age=7200"},
        )
