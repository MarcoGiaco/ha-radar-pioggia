"""Constants for the Radar pioggia integration."""

DOMAIN = "radar_pioggia"

MAPS_URL = "https://api.rainviewer.com/public/weather-maps.json"
# Radar-DPC: the same endpoints the official viewer radar.protezionecivile.it uses.
DPC_API_URL = "https://radar-api.protezionecivile.it"
DPC_TILE_URL = (
    "https://s3-prod-dpc-radar-webp-cache.s3.eu-south-1.amazonaws.com"
    "/{product}/{date}/{hhmm}/{z}/{x}/{y}/{name}.webp"
)
USER_AGENT = "HomeAssistant-radar_pioggia/0.2"
ATTRIBUTION = "Radar: Dipartimento della Protezione Civile (CC BY-SA 4.0) · RainViewer.com"

SOURCE_DPC = "Radar-DPC"
SOURCE_RAINVIEWER = "RainViewer"

CONF_RADIUS = "raggio"
CONF_LEAD = "preavviso"

# km around the point that are analysed.
DEFAULT_RADIUS = 60
MIN_RADIUS = 20
MAX_RADIUS = 150

# Minutes: "Pioggia in arrivo" turns on when the estimated arrival is within this.
DEFAULT_LEAD = 45
MIN_LEAD = 15
MAX_LEAD = 90

# km: "Temporale vicino" turns on when a storm echo (>= 45 dBZ) is this close.
STORM_NEAR_KM = 30

# Radar-DPC publishes a frame every 5 minutes (RainViewer every 10). Tiles are
# downloaded only when a new frame appears.
SCAN_INTERVAL_MIN = 5
# Frames analysed: the newest and the ones 10 and 20 minutes before it.
FRAMES = 3
FRAME_STEP_MIN = 10
DPC_STEP_MIN = 5

# Radar map card: minutes of history shown, and forecast frames obtained by
# moving the newest frame along the measured motion.
HISTORY_MIN = 60
FORECAST_MIN = 60
FORECAST_STEP_MIN = 10
