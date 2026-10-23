"""Sensors for Radar pioggia."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength, UnitOfSpeed, UnitOfTime, UnitOfVolumetricFlux
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .analysis import RadarResult, compass, intensity_label, precip_kind, rain_rate
from .coordinator import RadarConfigEntry, RadarCoordinator
from .entity import RadarEntity


@dataclass(frozen=True, kw_only=True)
class RadarSensorDescription(SensorEntityDescription):
    """Sensor reading one value from the radar analysis."""

    value_fn: Callable[[RadarResult], Any]
    attrs_fn: Callable[[RadarResult], dict[str, Any]] | None = None


SENSORS: tuple[RadarSensorDescription, ...] = (
    RadarSensorDescription(
        key="pioggia_attuale",
        translation_key="pioggia_attuale",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        value_fn=lambda r: rain_rate(r.over_point_dbz) or 0.0,
        attrs_fn=lambda r: {
            "dbz": r.over_point_dbz,
            "intensita": intensity_label(r.over_point_dbz),
            "tipo": precip_kind(r.over_point_snow) if r.over_point_dbz is not None else None,
        },
    ),
    RadarSensorDescription(
        key="distanza_pioggia",
        translation_key="distanza_pioggia",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=0,
        value_fn=lambda r: r.nearest_km,
        attrs_fn=lambda r: {
            "direzione": compass(r.nearest_bearing),
            "direzione_gradi": r.nearest_bearing,
            "intensita": intensity_label(r.nearest_dbz),
            "mm_h": rain_rate(r.nearest_dbz),
            "dbz": r.nearest_dbz,
            "in_avvicinamento": r.approaching,
        },
    ),
    RadarSensorDescription(
        key="arrivo_pioggia",
        translation_key="arrivo_pioggia",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda r: r.eta_min,
        attrs_fn=lambda r: {
            "ora": r.eta_time.isoformat() if r.eta_time else None,
            "intensita": intensity_label(r.eta_dbz),
            "mm_h": rain_rate(r.eta_dbz),
            "dbz": r.eta_dbz,
            "tipo": precip_kind(r.eta_snow) if r.eta_min is not None else None,
            "provenienza": compass(r.moving_from),
        },
    ),
    RadarSensorDescription(
        key="spostamento",
        translation_key="spostamento",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        value_fn=lambda r: r.speed_kmh,
        attrs_fn=lambda r: {
            "provenienza": compass(r.moving_from),
            "provenienza_gradi": r.moving_from,
        },
    ),
    RadarSensorDescription(
        key="pioggia_massima",
        translation_key="pioggia_massima",
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        value_fn=lambda r: rain_rate(r.strongest_dbz) or 0.0,
        attrs_fn=lambda r: {
            "intensita": intensity_label(r.strongest_dbz),
            "dbz": r.strongest_dbz,
            "distanza_km": r.strongest_km,
            "direzione": compass(r.strongest_bearing),
        },
    ),
    RadarSensorDescription(
        key="ora_radar",
        translation_key="ora_radar",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda r: r.time,
        attrs_fn=lambda r: {"fonte": r.source},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RadarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(RadarSensor(coordinator, desc) for desc in SENSORS)


class RadarSensor(RadarEntity, SensorEntity):
    """One value from the radar analysis."""

    entity_description: RadarSensorDescription

    def __init__(self, coordinator: RadarCoordinator, description: RadarSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
