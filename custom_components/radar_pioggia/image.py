"""Image entity for Radar pioggia: the newest radar frame over a map, e.g. for notifications."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import RadarConfigEntry, RadarCoordinator
from .entity import RadarEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the radar map picture."""
    async_add_entities([RadarMapImage(hass, entry.runtime_data)])


class RadarMapImage(RadarEntity, ImageEntity):
    """Newest radar frame drawn over OpenStreetMap, the point in red."""

    _attr_content_type = "image/png"
    _attr_translation_key = "mappa_radar"

    def __init__(self, hass: HomeAssistant, coordinator: RadarCoordinator) -> None:
        super().__init__(coordinator, "mappa_radar")
        ImageEntity.__init__(self, hass)
        self._attr_image_last_updated = self._frame_time()

    def _frame_time(self) -> datetime | None:
        frame = self.coordinator.latest_frame
        return frame.time if frame else None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_image_last_updated = self._frame_time()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        time = self._frame_time()
        if time is None:
            return None
        return await self.coordinator.async_map_png(dt_util.as_local(time).strftime("%d/%m %H:%M"))
