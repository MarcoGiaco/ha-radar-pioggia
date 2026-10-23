"""Constants for the Radar pioggia integration."""

DOMAIN = "radar_pioggia"

MAPS_URL = "https://api.rainviewer.com/public/weather-maps.json"
# Radar-DPC: the same endpoints the official viewer radar.protezionecivile.it uses.
DPC_API_URL = "https://radar-api.protezionecivile.it"
DPC_TILE_URL = (
    "https://s3-prod-dpc-radar-webp-cache.s3.eu-south-1.amazonaws.com"
    "/{product}/{date}/{hhmm}/{z}/{x}/{y}/{name}.webp"
)
USER_AGENT = "HomeAssistant-radar_pioggia/0.4 (+https://github.com/MarcoGiaco/ha-radar-pioggia)"
# Base map of the radar picture (image entity), OpenStreetMap standard tiles.
BASEMAP_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
BASEMAP_ATTRIBUTION = "© OpenStreetMap"
ATTRIBUTION = "Radar: Dipartimento della Protezione Civile (CC BY-SA 4.0) · RainViewer.com"

SOURCE_DPC = "Radar-DPC"
SOURCE_RAINVIEWER = "RainViewer"

CONF_RADIUS = "raggio"
CONF_LEAD = "preavviso"
CONF_ALERT_KM = "distanza_arrivo"
CONF_HIDE_WEAK = "nascondi_deboli"

# km around the point that are analysed.
DEFAULT_RADIUS = 60
MIN_RADIUS = 20
MAX_RADIUS = 150

# Minutes: "Pioggia in arrivo" turns on when the estimated arrival is within this.
DEFAULT_LEAD = 45
MIN_LEAD = 15
MAX_LEAD = 90

# km: the rain counts as arrived (Arrivo pioggia = 0) within this distance of the point.
DEFAULT_ALERT_KM = 3
MIN_ALERT_KM = 1
MAX_ALERT_KM = 30

# dBZ: with "nascondi_deboli" the map leaves weaker echoes transparent
# (drizzle or rain that does not reach the ground).
WEAK_DBZ = 15

# km: "Temporale vicino" turns on when a storm echo (>= 45 dBZ) is this close.
STORM_NEAR_KM = 30

# Radar-DPC publishes a frame every 5 minutes (RainViewer every 10). Tiles are
# downloaded only when a new frame appears.
SCAN_INTERVAL_MIN = 5
# Radar-DPC: a frame appears about this many minutes after its nominal time
# (8 on 23/10/2026; then learned). While a frame is due the newest product is
# checked every FAST_POLL_S seconds, so it is used within that time.
DPC_DELAY_MIN = 8
FAST_POLL_S = 30
# Frames analysed: the newest and the ones 10 and 20 minutes before it.
FRAMES = 3
FRAME_STEP_MIN = 10
DPC_STEP_MIN = 5

# Radar map card: minutes of history shown, and forecast frames obtained by
# moving the newest frame along the measured motion.
HISTORY_MIN = 60
FORECAST_MIN = 60
FORECAST_STEP_MIN = 10
