"""Radar pioggia: rain radar nowcast for one point, from Radar-DPC or RainViewer."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .coordinator import RadarConfigEntry, RadarCoordinator
from .http import RadarFramesView, RadarImageView

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.IMAGE, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
CARD_URL = "/radar_pioggia/radar-pioggia-card.js"

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the map card and its data."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "frontend" / "radar-pioggia-card.js"), False)]
    )
    url = await _async_card_url(hass)
    if not await _async_register_resource(hass, url):
        add_extra_js_url(hass, url)
    hass.http.register_view(RadarFramesView())
    hass.http.register_view(RadarImageView())
    return True


async def _async_card_url(hass: HomeAssistant) -> str:
    """The card's address; the version in it makes browsers load the new card after an update."""
    integration = await async_get_integration(hass, DOMAIN)
    return f"{CARD_URL}?v={integration.version}"


async def _async_register_resource(hass: HomeAssistant, url: str) -> bool:
    """Add the card to the dashboard resources, as HACS does for its cards.

    The frontend loads resources each time it connects, so a card that failed
    to load (the phone app woke up before the network) is loaded again; an
    extra JS URL is imported only once, when the page opens. Returns False
    when resources are kept in YAML, and the extra JS URL is used instead.
    """
    try:
        if (found := await _async_our_resources(hass)) is None:
            return False
        resources, ours = found
        if not ours:
            await resources.async_create_item({"res_type": "module", "url": url})
        elif ours[0]["url"] != url:
            await resources.async_update_item(ours[0]["id"], {"res_type": "module", "url": url})
        for extra in ours[1:]:
            await resources.async_delete_item(extra["id"])
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Card not added to the dashboard resources, loaded as extra JS", exc_info=True)
        return False
    return True


async def _async_our_resources(hass: HomeAssistant):
    """The dashboard resources and the card's entries in them; None in YAML mode."""
    lovelace = hass.data[LOVELACE_DATA]
    if lovelace.resource_mode != "storage":
        return None
    resources = lovelace.resources
    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True
    return resources, [r for r in resources.async_items() if r["url"].split("?")[0] == CARD_URL]


async def async_setup_entry(hass: HomeAssistant, entry: RadarConfigEntry) -> bool:
    """Set up radar analysis for one point."""
    # Back in the resources if the last point was removed and a new one added.
    await _async_register_resource(hass, await _async_card_url(hass))
    coordinator = RadarCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RadarConfigEntry) -> bool:
    """Unload radar analysis for one point."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: RadarConfigEntry) -> None:
    """Take the card out of the dashboard resources when the last point goes."""
    if any(e.entry_id != entry.entry_id for e in hass.config_entries.async_entries(DOMAIN)):
        return
    try:
        if (found := await _async_our_resources(hass)) is None:
            return
        resources, ours = found
        for item in ours:
            await resources.async_delete_item(item["id"])
    except Exception:  # noqa: BLE001
        _LOGGER.warning("Card not removed from the dashboard resources", exc_info=True)


async def _async_reload(hass: HomeAssistant, entry: RadarConfigEntry) -> None:
    """Reload when the options (radius, lead time) change."""
    await hass.config_entries.async_reload(entry.entry_id)
