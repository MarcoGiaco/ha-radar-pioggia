"""Base entity for Radar pioggia."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import RadarCoordinator


class RadarEntity(CoordinatorEntity[RadarCoordinator]):
    """Common device and attribution for one point."""

    _attr_attribution = ATTRIBUTION
    _attr_has_entity_name = True

    def __init__(self, coordinator: RadarCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Radar pioggia {entry.title}",
            manufacturer="RainViewer.com",
            model="Radar e nowcast",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://www.rainviewer.com/map.html",
        )
