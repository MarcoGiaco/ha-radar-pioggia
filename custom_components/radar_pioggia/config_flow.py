"""Config flow for Radar pioggia: pick a point (default: home) and a name."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    LocationSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    BASEMAPS,
    CONF_ALERT_KM,
    CONF_BASEMAP,
    CONF_HIDE_WEAK,
    CONF_LEAD,
    CONF_RADIUS,
    DEFAULT_ALERT_KM,
    DEFAULT_BASEMAP,
    DEFAULT_LEAD,
    DEFAULT_RADIUS,
    DOMAIN,
    MAX_ALERT_KM,
    MAX_LEAD,
    MAX_RADIUS,
    MIN_ALERT_KM,
    MIN_LEAD,
    MIN_RADIUS,
)

CONF_LOCATION = "posizione"

# Coordinates Home Assistant uses when the home location was never set:
# 0/0, the core default (San Diego) and the onboarding map default (Amsterdam).
PLACEHOLDER_LOCATIONS = {(0.0, 0.0), (32.8734, -117.2274), (52.3731, 4.8903)}


def _is_placeholder(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return True
    return (round(lat, 4), round(lon, 4)) in PLACEHOLDER_LOCATIONS


class RadarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Radar pioggia."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the point to watch, starting from the home location set in Home Assistant."""
        errors: dict[str, str] = {}
        if user_input is not None:
            loc = user_input[CONF_LOCATION]
            lat, lon = round(loc[CONF_LATITUDE], 5), round(loc[CONF_LONGITUDE], 5)
            if _is_placeholder(lat, lon):
                errors[CONF_LOCATION] = "posizione_predefinita"
            else:
                await self.async_set_unique_id(f"{lat}_{lon}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={CONF_LATITUDE: lat, CONF_LONGITUDE: lon},
                )
        home_missing = _is_placeholder(self.hass.config.latitude, self.hass.config.longitude)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=self.hass.config.location_name): TextSelector(),
                    vol.Required(
                        CONF_LOCATION,
                        default={
                            CONF_LATITUDE: self.hass.config.latitude,
                            CONF_LONGITUDE: self.hass.config.longitude,
                        },
                    ): LocationSelector(),
                }
            ),
            errors=errors,
            description_placeholders={
                "avviso": (
                    "⚠️ La posizione di casa non è impostata in Home Assistant "
                    "(Impostazioni → Sistema → Generale): sposta il punto sulla mappa "
                    "oppure imposta prima la posizione di casa."
                    if home_missing
                    else ""
                )
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Options: radius, lead time, arrival distance and map."""
        return RadarOptionsFlow()


class RadarOptionsFlow(OptionsFlow):
    """Change the analysed radius, when 'Pioggia in arrivo' turns on, when the rain counts as arrived and the map."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_RADIUS: int(user_input[CONF_RADIUS]),
                    CONF_LEAD: int(user_input[CONF_LEAD]),
                    CONF_ALERT_KM: int(user_input[CONF_ALERT_KM]),
                    CONF_HIDE_WEAK: bool(user_input[CONF_HIDE_WEAK]),
                    CONF_BASEMAP: user_input[CONF_BASEMAP],
                }
            )
        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_RADIUS, default=opts.get(CONF_RADIUS, DEFAULT_RADIUS)): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_RADIUS, max=MAX_RADIUS, step=10,
                            unit_of_measurement="km", mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(CONF_LEAD, default=opts.get(CONF_LEAD, DEFAULT_LEAD)): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_LEAD, max=MAX_LEAD, step=5,
                            unit_of_measurement="min", mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(CONF_ALERT_KM, default=opts.get(CONF_ALERT_KM, DEFAULT_ALERT_KM)): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_ALERT_KM, max=MAX_ALERT_KM, step=1,
                            unit_of_measurement="km", mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(CONF_HIDE_WEAK, default=opts.get(CONF_HIDE_WEAK, False)): BooleanSelector(),
                    vol.Required(CONF_BASEMAP, default=opts.get(CONF_BASEMAP, DEFAULT_BASEMAP)): SelectSelector(
                        SelectSelectorConfig(
                            options=list(BASEMAPS), translation_key=CONF_BASEMAP, mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }
            ),
        )

