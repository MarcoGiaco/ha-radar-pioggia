"""Radar image analysis: decode radar tiles, nowcast rain at one point, render map frames.

No Home Assistant imports, so it can be tested on its own. Steps:
1. stitch the zoom-7 tiles around the point and crop a square of the chosen radius;
2. turn colors back into dBZ (rain and snow separately);
3. find the nearest echo, the strongest one and what is over the point now;
4. estimate how the rain field moves by matching two frames 20 minutes apart;
5. move the newest field forward in 5-minute steps to see if and when it reaches the point.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import io
import math

import numpy as np
from PIL import Image

from .colors import RAIN, SNOW

ZOOM = 7
TILE = 256
EARTH_KM = 40075.016686

# dBZ thresholds. 20 dBZ is about 0.6 mm/h, the weakest rain that usually reaches the ground.
RAIN_DBZ = 20
STORM_DBZ = 45
# The point counts as "hit" when an echo comes within this distance.
HIT_KM = 3.0
# A pixel counts only with at least this many echoes in its 3x3 block (drops lone speckles).
MIN_NEIGHBOURS = 3
LEAD_STEP_MIN = 5
MAX_LEAD_MIN = 90
# Fastest motion we look for, km/h.
MAX_SPEED_KMH = 110

COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
           "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]


def compass(deg: float | None) -> str | None:
    """Italian 16-point compass name for a bearing."""
    if deg is None:
        return None
    return COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


def rain_rate(dbz: float | None) -> float | None:
    """Marshall-Palmer: Z = 200 R^1.6, R in mm/h."""
    if dbz is None or (isinstance(dbz, float) and math.isnan(dbz)):
        return None
    return round((10 ** (dbz / 10) / 200) ** (1 / 1.6), 1)


def intensity_label(dbz: float | None) -> str | None:
    if dbz is None:
        return None
    if dbz >= STORM_DBZ:
        return "temporale"
    if dbz >= 35:
        return "forte"
    if dbz >= 28:
        return "moderata"
    return "debole"


def global_pixel(lat: float, lon: float, zoom: int = ZOOM) -> tuple[float, float]:
    """Web Mercator pixel coordinates of a point."""
    n = TILE * 2**zoom
    x = (lon + 180) / 360 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def km_per_pixel(lat: float, zoom: int = ZOOM) -> float:
    return EARTH_KM * math.cos(math.radians(lat)) / (TILE * 2**zoom)


@dataclass(frozen=True)
class Window:
    """The square of pixels analysed around the point."""

    x0: int
    y0: int
    size: int
    km_px: float

    @property
    def center(self) -> float:
        return (self.size - 1) / 2

    def tiles(self) -> list[tuple[int, int]]:
        tx = range(self.x0 // TILE, (self.x0 + self.size - 1) // TILE + 1)
        ty = range(self.y0 // TILE, (self.y0 + self.size - 1) // TILE + 1)
        return [(x, y) for y in ty for x in tx]


def make_window(lat: float, lon: float, radius_km: float) -> Window:
    km_px = km_per_pixel(lat)
    r = math.ceil(radius_km / km_px)
    gx, gy = global_pixel(lat, lon)
    cx, cy = int(gx), int(gy)
    return Window(cx - r, cy - r, 2 * r + 1, km_px)


def decode_tile(png: bytes) -> tuple[np.ndarray, np.ndarray]:
    """dBZ array (NaN = no echo) and snow mask for one tile."""
    rgba = np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"), dtype=np.uint32)
    packed = (rgba[..., 0] << 24) | (rgba[..., 1] << 16) | (rgba[..., 2] << 8) | rgba[..., 3]
    dbz = np.full(packed.shape, np.nan, dtype=np.float32)
    snow = np.zeros(packed.shape, dtype=bool)
    for value in np.unique(packed):
        v = int(value)
        if v in RAIN:
            dbz[packed == value] = RAIN[v]
        elif v in SNOW:
            sel = packed == value
            dbz[sel] = SNOW[v]
            snow[sel] = True
    return dbz, snow


DPC_MAX_DBZ = 60.0


def decode_dpc_tile(webp: bytes) -> tuple[np.ndarray, np.ndarray]:
    """dBZ array (NaN = no echo or no coverage) for one Radar-DPC VMI tile.

    The tiles are grayscale: red channel 0..255 maps linearly to 0..60 dBZ,
    alpha 0 marks areas the radar network does not cover. No snow information.
    """
    rgba = np.asarray(Image.open(io.BytesIO(webp)).convert("RGBA"), dtype=np.float32)
    dbz = rgba[..., 0] / 255 * DPC_MAX_DBZ
    dbz[(rgba[..., 3] == 0) | (dbz <= 0)] = np.nan
    return dbz, np.zeros(dbz.shape, dtype=bool)


def build_field(
    window: Window,
    tiles: dict[tuple[int, int], bytes | None],
    decoder=decode_tile,
) -> tuple[np.ndarray, np.ndarray]:
    """Stitch decoded tiles and crop the window. A missing tile (None) counts as no echo."""
    keys = window.tiles()
    xs = sorted({k[0] for k in keys})
    ys = sorted({k[1] for k in keys})
    dbz = np.full((len(ys) * TILE, len(xs) * TILE), np.nan, dtype=np.float32)
    snow = np.zeros(dbz.shape, dtype=bool)
    for (tx, ty) in keys:
        if tiles[(tx, ty)] is None:
            continue
        d, s = decoder(tiles[(tx, ty)])
        oy, ox = (ty - ys[0]) * TILE, (tx - xs[0]) * TILE
        dbz[oy:oy + TILE, ox:ox + TILE] = d
        snow[oy:oy + TILE, ox:ox + TILE] = s
    ox = window.x0 - xs[0] * TILE
    oy = window.y0 - ys[0] * TILE
    sl = (slice(oy, oy + window.size), slice(ox, ox + window.size))
    return dbz[sl], snow[sl]


def _echo_mask(dbz: np.ndarray, threshold: float) -> np.ndarray:
    """Echoes at or above `threshold` that have enough neighbours."""
    m = np.nan_to_num(dbz, nan=-99) >= threshold
    padded = np.pad(m, 1).astype(np.int8)
    count = sum(
        padded[1 + dy:1 + dy + m.shape[0], 1 + dx:1 + dx + m.shape[1]]
        for dy in (-1, 0, 1) for dx in (-1, 0, 1)
    )
    return m & (count >= MIN_NEIGHBOURS)


@dataclass
class Frame:
    time: datetime
    dbz: np.ndarray
    snow: np.ndarray


@dataclass
class RadarResult:
    """What the radar says about the point."""

    time: datetime
    over_point_dbz: float | None
    over_point_snow: bool
    nearest_km: float | None
    nearest_bearing: float | None
    nearest_dbz: float | None
    strongest_dbz: float | None
    strongest_km: float | None
    strongest_bearing: float | None
    speed_kmh: float | None
    moving_from: float | None
    eta_min: int | None
    eta_dbz: float | None
    eta_snow: bool
    approaching: bool
    storm_km: float | None
    source: str = ""
    # Motion of the rain field, pixels per minute (x east, y south); None if unknown.
    velocity: tuple[float, float] | None = None


def _polar(window: Window) -> tuple[np.ndarray, np.ndarray]:
    """Distance (km) and bearing (deg) of every pixel from the point."""
    idx = np.arange(window.size) - window.center
    dx, dy = np.meshgrid(idx, idx)
    dist = np.hypot(dx, dy) * window.km_px
    bearing = (np.degrees(np.arctan2(dx, -dy)) + 360) % 360
    return dist, bearing


def _motion(prev: np.ndarray, cur: np.ndarray, minutes: float, km_px: float) -> tuple[float, float] | None:
    """Pixel displacement per minute (dx, dy) that best maps prev onto cur.

    Works on 2x2 block maxima to keep it fast; needs some rain in both frames.
    """
    def coarse(a: np.ndarray) -> np.ndarray:
        n = a.shape[0] // 2 * 2
        b = np.nan_to_num(a[:n, :n], nan=0)
        b = np.clip(b - 10, 0, None)  # weight by intensity above 10 dBZ
        return b.reshape(n // 2, 2, n // 2, 2).max(axis=(1, 3))

    a, b = coarse(prev), coarse(cur)
    if (a > RAIN_DBZ - 10).sum() < 20 or (b > RAIN_DBZ - 10).sum() < 20:
        return None
    max_shift = int(MAX_SPEED_KMH * minutes / 60 / (km_px * 2)) + 1
    n = a.shape[0]
    best, best_score = None, 0.0
    for sy in range(-max_shift, max_shift + 1):
        for sx in range(-max_shift, max_shift + 1):
            ya, yb = max(0, -sy), max(0, sy)
            xa, xb = max(0, -sx), max(0, sx)
            h, w = n - abs(sy), n - abs(sx)
            if h < n // 2 or w < n // 2:
                continue
            pa = a[ya:ya + h, xa:xa + w]
            pb = b[yb:yb + h, xb:xb + w]
            denom = math.sqrt(float((pa * pa).sum()) * float((pb * pb).sum()))
            if denom == 0:
                continue
            score = float((pa * pb).sum()) / denom
            if score > best_score:
                best, best_score = (sx, sy), score
    if best is None or best_score < 0.3:
        return None
    return best[0] * 2 / minutes, best[1] * 2 / minutes


def analyse(frames: list[Frame], window: Window) -> RadarResult:
    """Analyse the frames (oldest first) for the point at the window centre."""
    cur = frames[-1]
    dist, bearing = _polar(window)
    valid = _echo_mask(cur.dbz, RAIN_DBZ)

    near_point = dist <= HIT_KM
    over = np.where(near_point & valid, cur.dbz, np.nan)
    over_dbz = float(np.nanmax(over)) if np.isfinite(over).any() else None
    over_snow = bool((cur.snow & near_point & valid).any())

    nearest_km = nearest_bearing = nearest_dbz = None
    if valid.any():
        d = np.where(valid, dist, np.inf)
        i = np.unravel_index(int(np.argmin(d)), d.shape)
        nearest_km = float(d[i])
        nearest_bearing = float(bearing[i])
        around = valid & (np.hypot(*np.subtract(np.indices(d.shape), np.array(i)[:, None, None])) * window.km_px <= 5)
        nearest_dbz = float(np.nanmax(np.where(around, cur.dbz, np.nan)))

    strongest_dbz = strongest_km = strongest_bearing = None
    storm_km = None
    in_radius = valid & (dist <= window.size / 2 * window.km_px)
    if in_radius.any():
        s = np.where(in_radius, cur.dbz, -np.inf)
        i = np.unravel_index(int(np.argmax(s)), s.shape)
        strongest_dbz = float(s[i])
        strongest_km = float(dist[i])
        strongest_bearing = float(bearing[i])
        storm = in_radius & (np.nan_to_num(cur.dbz, nan=-99) >= STORM_DBZ)
        if storm.any():
            storm_km = float(dist[storm].min())

    # Motion from the frame ~20 min before (or the oldest available).
    speed = moving_from = None
    vel = None
    if len(frames) >= 2:
        old = frames[0]
        minutes = (cur.time - old.time).total_seconds() / 60
        if minutes > 0:
            vel = _motion(old.dbz, cur.dbz, minutes, window.km_px)
    if vel is not None:
        vx, vy = vel
        speed = math.hypot(vx, vy) * window.km_px * 60
        # Direction the rain comes from = opposite of where it goes.
        moving_from = (math.degrees(math.atan2(-vx, vy)) + 360) % 360
        if speed < 3:
            speed, moving_from = round(speed, 1), None

    # Nowcast: which echo ends up over the point after `lead` minutes?
    eta = eta_dbz = None
    eta_snow = False
    if over_dbz is not None:
        eta, eta_dbz, eta_snow = 0, over_dbz, over_snow
    elif vel is not None and valid.any():
        ys, xs = np.nonzero(valid)
        for lead in range(LEAD_STEP_MIN, MAX_LEAD_MIN + 1, LEAD_STEP_MIN):
            px = xs + vel[0] * lead - window.center
            py = ys + vel[1] * lead - window.center
            hit = np.hypot(px, py) * window.km_px <= HIT_KM
            if hit.any():
                eta = lead
                eta_dbz = float(cur.dbz[ys[hit], xs[hit]].max())
                eta_snow = bool(cur.snow[ys[hit], xs[hit]].any())
                break

    approaching = eta is not None and eta > 0
    if not approaching and len(frames) >= 2 and nearest_km is not None:
        prev_valid = _echo_mask(frames[-2].dbz, RAIN_DBZ)
        if prev_valid.any():
            prev_near = float(dist[prev_valid].min())
            approaching = nearest_km < prev_near - 1.5

    def r1(v):
        return None if v is None else round(v, 1)

    return RadarResult(
        time=cur.time,
        over_point_dbz=r1(over_dbz),
        over_point_snow=over_snow,
        nearest_km=r1(nearest_km),
        nearest_bearing=None if nearest_bearing is None else round(nearest_bearing),
        nearest_dbz=r1(nearest_dbz),
        strongest_dbz=r1(strongest_dbz),
        strongest_km=r1(strongest_km),
        strongest_bearing=None if strongest_bearing is None else round(strongest_bearing),
        speed_kmh=None if speed is None else round(speed),
        moving_from=None if moving_from is None else round(moving_from),
        eta_min=eta,
        eta_dbz=r1(eta_dbz),
        eta_snow=eta_snow,
        approaching=approaching,
        storm_km=r1(storm_km),
        velocity=vel,
    )


def frame_time(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


# Colors for the map frames: lower dBZ bound -> RGBA. Echoes below the first
# step are left transparent (mostly ground clutter and virga).
RAIN_COLORS = [
    (8, (156, 214, 252, 130)),
    (15, (90, 170, 250, 180)),
    (20, (40, 120, 240, 205)),
    (25, (20, 75, 215, 215)),
    (30, (30, 175, 60, 220)),
    (35, (245, 215, 30, 225)),
    (40, (250, 145, 20, 230)),
    (45, (230, 40, 30, 235)),
    (50, (165, 0, 40, 235)),
    (55, (215, 40, 215, 235)),
]
SNOW_COLORS = [
    (8, (230, 230, 255, 140)),
    (20, (205, 195, 255, 190)),
    (30, (170, 140, 255, 215)),
    (40, (140, 90, 240, 230)),
]


def _paint(rgba: np.ndarray, dbz: np.ndarray, mask: np.ndarray, colors) -> None:
    for lower, color in colors:
        rgba[mask & (dbz >= lower)] = color


def render_png(dbz: np.ndarray, snow: np.ndarray) -> bytes:
    """RGBA PNG of one frame, same pixels as the analysed window."""
    rgba = np.zeros(dbz.shape + (4,), dtype=np.uint8)
    d = np.nan_to_num(dbz, nan=-99)
    _paint(rgba, d, ~snow, RAIN_COLORS)
    _paint(rgba, d, snow, SNOW_COLORS)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def advect(dbz: np.ndarray, snow: np.ndarray, velocity: tuple[float, float], minutes: float):
    """Shift the field along the motion vector (simple persistence nowcast)."""
    dx = int(round(velocity[0] * minutes))
    dy = int(round(velocity[1] * minutes))
    out_d = np.full(dbz.shape, np.nan, dtype=dbz.dtype)
    out_s = np.zeros(snow.shape, dtype=bool)
    h, w = dbz.shape
    if abs(dx) >= w or abs(dy) >= h:
        return out_d, out_s
    src_y = slice(max(0, -dy), h - max(0, dy))
    src_x = slice(max(0, -dx), w - max(0, dx))
    dst_y = slice(max(0, dy), h - max(0, -dy))
    dst_x = slice(max(0, dx), w - max(0, -dx))
    out_d[dst_y, dst_x] = dbz[src_y, src_x]
    out_s[dst_y, dst_x] = snow[src_y, src_x]
    return out_d, out_s


def _pixel_to_latlon(gx: float, gy: float, zoom: int = ZOOM) -> tuple[float, float]:
    n = TILE * 2**zoom
    lon = gx / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * gy / n))))
    return lat, lon


def window_bounds(window: Window) -> list[list[float]]:
    """[[south, west], [north, east]] of the window, for a map image overlay."""
    north, west = _pixel_to_latlon(window.x0, window.y0)
    south, east = _pixel_to_latlon(window.x0 + window.size, window.y0 + window.size)
    return [[round(south, 5), round(west, 5)], [round(north, 5), round(east, 5)]]
