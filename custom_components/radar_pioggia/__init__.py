"""Radar pioggia: rain radar nowcast for one point, from Radar-DPC or RainViewer."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the map card and its data."""
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(Path(__file__).parent / "frontend" / "radar-pioggia-card.js"), False)]
    )
    # The version in the URL makes browsers load the new card after an update.
    add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")
    hass.http.register_view(RadarFramesView())
    hass.http.register_view(RadarImageView())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RadarConfigEntry) -> bool:
    """Set up radar analysis for one point."""
    coordinator = RadarCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RadarConfigEntry) -> bool:
    """Unload radar analysis for one point."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: RadarConfigEntry) -> None:
    """Reload when the options (radius, lead time) change."""
    await hass.config_entries.async_reload(entry.entry_id)
