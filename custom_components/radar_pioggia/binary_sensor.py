"""Binary sensors for Radar pioggia: rain on its way, storm nearby."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .analysis import RadarResult, compass, intensity_label, rain_rate
from .const import CONF_LEAD, DEFAULT_LEAD, STORM_NEAR_KM
from .coordinator import RadarConfigEntry, RadarCoordinator
from .entity import RadarEntity


@dataclass(frozen=True, kw_only=True)
class RadarBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor computed from the radar analysis and the lead time."""

    is_on_fn: Callable[[RadarResult, int], bool]
    attrs_fn: Callable[[RadarResult], dict[str, Any]]


BINARY_SENSORS: tuple[RadarBinaryDescription, ...] = (
    RadarBinaryDescription(
        key="pioggia_in_arrivo",
        translation_key="pioggia_in_arrivo",
        is_on_fn=lambda r, lead: r.eta_min is not None and 0 < r.eta_min <= lead,
        attrs_fn=lambda r: {
            "minuti": r.eta_min,
            "ora": (r.time + timedelta(minutes=r.eta_min)).isoformat() if r.eta_min is not None else None,
            "intensita": intensity_label(r.eta_dbz),
            "mm_h": rain_rate(r.eta_dbz),
            "tipo": ("neve" if r.eta_snow else "pioggia") if r.eta_min is not None else None,
            "provenienza": compass(r.moving_from),
            "velocita_kmh": r.speed_kmh,
        },
    ),
    RadarBinaryDescription(
        key="temporale_vicino",
        translation_key="temporale_vicino",
        is_on_fn=lambda r, lead: r.storm_km is not None and r.storm_km <= STORM_NEAR_KM,
        attrs_fn=lambda r: {
            "distanza_km": r.storm_km,
            "direzione": compass(r.strongest_bearing) if r.storm_km is not None else None,
            "provenienza": compass(r.moving_from),
            "velocita_kmh": r.speed_kmh,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(RadarBinarySensor(coordinator, desc) for desc in BINARY_SENSORS)


class RadarBinarySensor(RadarEntity, BinarySensorEntity):
    """On/off from the radar analysis."""

    entity_description: RadarBinaryDescription

    def __init__(self, coordinator: RadarCoordinator, description: RadarBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        lead = self.coordinator.config_entry.options.get(CONF_LEAD, DEFAULT_LEAD)
        return self.entity_description.is_on_fn(self.coordinator.data, lead)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs_fn(self.coordinator.data)
