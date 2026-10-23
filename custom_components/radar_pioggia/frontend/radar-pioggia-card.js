// Radar pioggia map card: radar frames of the last hour and the estimated
// next hour over a map, with a time slider and play button.
//
//   type: custom:radar-pioggia-card
//   entity: sensor.radar_pioggia_casa_ora_radar   # any entity of the point
//   title: Radar        # header text; leave out for no header
//   icon: mdi:radar     # header icon
//   color: "#e57373"    # header icon colour and background tint; a theme
//                       # colour name (red, primary…) works too. Leave out
//                       # for the theme's plain card background.
//   bare: true          # no card background, to sit inside another card
//   zoom: 8             # initial map zoom
//   tile_url: https://…/{z}/{x}/{y}.png   # other basemap; OpenStreetMap if left out
//   tile_attribution: "© …"              # credit shown for that basemap

const LEAFLET = "https://unpkg.com/leaflet@1.9.4/dist/";
// Default basemap: OpenStreetMap tiles (tile_url replaces them). In the dark
// theme they are inverted with a CSS filter.
const BASEMAP = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const MAP_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const STEP_MS = 700;
const HOLD_MS = 1500;
const REFRESH_MS = 5 * 60 * 1000;
// After a failed load, try again after these delays (the last one repeats).
const RETRY_MS = [5000, 15000, 30000, 60000];
// A request that hangs (the phone app was suspended mid-request) gives up
// after this long, so it cannot block every later load.
const TIMEOUT_MS = 20000;

const withTimeout = (promise, ms = TIMEOUT_MS) =>
  Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), ms))]);

let leafletReady;
function loadLeaflet() {
  if (window.L) return Promise.resolve();
  if (!leafletReady) {
    leafletReady = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = LEAFLET + "leaflet.js";
      s.onload = resolve;
      s.onerror = () => { leafletReady = undefined; s.remove(); reject(new Error("Leaflet non caricato")); };
      document.head.appendChild(s);
    });
  }
  return withTimeout(leafletReady).catch((err) => {
    if (!window.L) leafletReady = undefined;
    throw err;
  });
}

const hhmm = (d) => d.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });

// "red" or "primary" (as given by the colour picker) become theme variables;
// "#e57373", "rgb(…)" and "var(…)" are used as they are.
const cssColor = (c) => (!c || c === "none" ? null : /^(#|rgb|hsl|var\()/.test(c) ? c : `var(--${c}-color)`);

// The radar time entity of the first point, for a new card.
function defaultEntity(hass) {
  const reg = Object.values(hass.entities || {}).find(
    (e) => e.platform === "radar_pioggia" && e.entity_id.endsWith("_ora_radar")
  );
  return reg ? reg.entity_id : Object.keys(hass.states).find((id) => /^sensor\.radar_pioggia_.*_ora_radar$/.test(id));
}

class RadarPioggiaCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("Serve 'entity': un'entità dell'integrazione Radar pioggia");
    this._config = { zoom: 8, bare: false, icon: "mdi:radar", ...config };
    this._stop();
    if (this._map) this._map.remove();
    this._map = this._base = undefined;
    if (this._resize) this._resize.disconnect();
    for (const url of (this._images || new Map()).values()) URL.revokeObjectURL(url);
    this._frames = [];
    this._images = new Map();
    this._index = 0;
    // The editor calls this again on every change: draw the card again.
    if (this._hass) {
      this._build();
      this._stamp = undefined;
      this.hass = this._hass;
    }
  }

  static getConfigElement() {
    return document.createElement("radar-pioggia-card-editor");
  }

  static getStubConfig(hass) {
    return { entity: defaultEntity(hass) || "", title: "Radar" };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._build();
    const dark = !!hass.themes?.darkMode;
    if (this._map && dark !== this._dark) this._setBasemap(dark);
    const st = hass.states[this._config.entity];
    const stamp = st ? st.last_updated : null;
    if (stamp !== this._stamp) {
      this._stamp = stamp;
      this._load();
    }
  }

  getCardSize() { return 7; }
  getGridOptions() { return { columns: "full", rows: 9, min_rows: 6 }; }

  connectedCallback() {
    this._timer = setInterval(() => this._load(), REFRESH_MS);
    // Back from the background (phone app reopened): load again at once.
    this._onVisible = () => {
      if (document.hidden) return;
      if (this._map) this._map.invalidateSize();
      this._load();
    };
    document.addEventListener("visibilitychange", this._onVisible);
    if (this._map) setTimeout(() => this._map.invalidateSize(), 0);
    if (this._hass && !this._frames.length) this._load();
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    clearTimeout(this._retryTimer);
    document.removeEventListener("visibilitychange", this._onVisible);
    this._stop();
  }

  _build() {
    const root = this.shadowRoot || this.attachShadow({ mode: "open" });
    const { bare, title, icon } = this._config;
    const color = cssColor(this._config.color);
    const tint = color
      ? `background: linear-gradient(160deg, color-mix(in srgb, ${color} 16%, var(--card-background-color)) 0%, var(--card-background-color) 75%);`
      : "";
    root.innerHTML = `
      <link rel="stylesheet" href="${LEAFLET}leaflet.css">
      <style>
        :host { display: block; height: 100%; }
        ha-card { height: 100%; box-sizing: border-box; display: flex; flex-direction: column;
                  ${bare ? "background: none; box-shadow: none; border: none; padding: 0;" : `padding: 16px; ${tint}`} }
        .title { display: flex; align-items: center; font-size: 15px; font-weight: 500; letter-spacing: 0.02em; color: var(--secondary-text-color); margin-bottom: 12px; }
        .title ha-icon { --mdc-icon-size: 20px; color: ${color || "var(--primary-color)"}; margin-right: 8px; }
        .wrap { flex: 1; display: flex; flex-direction: column; min-height: 300px; }
        #map { flex: 1; min-height: 240px; border-radius: 14px; overflow: hidden; z-index: 0; background: var(--secondary-background-color); }
        .leaflet-container { font-family: inherit; }
        .leaflet-image-layer { image-rendering: auto; transition: opacity 0.2s; }
        #map.dark .leaflet-tile-pane { filter: invert(1) hue-rotate(180deg) brightness(0.85) contrast(0.9) saturate(0.6); }
        #map.dark .leaflet-control-attribution { background: rgba(0,0,0,0.55); color: #bbb; }
        #map.dark .leaflet-control-attribution a { color: #ddd; }
        /* Map buttons follow the HA theme instead of Leaflet's white. */
        .leaflet-bar { border: none !important; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.3) !important; }
        .leaflet-bar a, .leaflet-bar a:hover { display: grid; place-items: center; width: 32px; height: 32px; line-height: 32px;
                 background: var(--card-background-color); color: var(--primary-text-color); border-bottom: 1px solid var(--divider-color); }
        .leaflet-bar a:last-child { border-bottom: none; }
        .leaflet-bar a:hover { background: color-mix(in srgb, var(--primary-color) 12%, var(--card-background-color)); }
        .leaflet-bar a.leaflet-disabled { background: var(--card-background-color); color: var(--disabled-text-color); }
        .leaflet-bar a ha-icon { --mdc-icon-size: 18px; color: var(--primary-color); }
        .home { width: 12px; height: 12px; border-radius: 50%; background: var(--primary-color); border: 2px solid #fff; box-shadow: 0 0 0 1px rgba(0,0,0,0.35); box-sizing: border-box; }
        .controls { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
        button { flex: none; width: 36px; height: 36px; border-radius: 50%; border: none; cursor: pointer; display: grid; place-items: center;
                 color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 16%, transparent); }
        button ha-icon { --mdc-icon-size: 20px; }
        input[type=range] { flex: 1; min-width: 0; accent-color: var(--primary-color); margin: 0; }
        .when { flex: none; min-width: 7.2em; text-align: right; font-variant-numeric: tabular-nums; font-size: 15px; font-weight: 500; letter-spacing: 0.02em; color: var(--secondary-text-color); white-space: nowrap; }
        .when.forecast { color: var(--primary-color); }
        .msg { position: absolute; inset: 0; display: grid; place-items: center; font-size: 15px; color: var(--secondary-text-color); pointer-events: none; z-index: 500; }
        .mapbox { position: relative; flex: 1; display: flex; flex-direction: column; min-height: 0; }
      </style>
      <ha-card>
        ${title ? `<div class="title"><ha-icon icon="${icon}"></ha-icon><span></span></div>` : ""}
        <div class="wrap">
          <div class="mapbox"><div id="map"></div><div class="msg">Carico il radar…</div></div>
          <div class="controls">
            <button title="Avvia / ferma"><ha-icon icon="mdi:play"></ha-icon></button>
            <input type="range" min="0" max="0" value="0" step="1">
            <div class="when">—</div>
          </div>
        </div>
      </ha-card>`;
    this._el = {
      map: root.getElementById("map"),
      msg: root.querySelector(".msg"),
      btn: root.querySelector("button"),
      icon: root.querySelector("button ha-icon"),
      range: root.querySelector("input"),
      when: root.querySelector(".when"),
    };
    if (title) root.querySelector(".title span").textContent = title;
    this._el.btn.addEventListener("click", () => (this._playing ? this._stop() : this._play()));
    this._el.range.addEventListener("input", () => { this._stop(); this._show(Number(this._el.range.value)); });
    this._resize = new ResizeObserver(() => {
      if (!this._map) return;
      this._map.invalidateSize();
      this._limitView();
    });
    this._resize.observe(this._el.map);
  }

  async _initMap(data) {
    await loadLeaflet();
    if (this._map) return;
    const L = window.L;
    this._area = L.latLngBounds(data.bounds);
    this._map = L.map(this._el.map, {
      zoomControl: true,
      scrollWheelZoom: false,
      attributionControl: true,
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      maxBounds: this._area,
      maxBoundsViscosity: 1,
    }).setView(data.center, this._config.zoom);
    this._limitView();
    this._map.attributionControl.setPrefix(false);
    this._setBasemap(!!this._hass.themes?.darkMode);
    this._center = data.center;
    const HomeControl = L.Control.extend({
      options: { position: "topleft" },
      onAdd: () => {
        const bar = L.DomUtil.create("div", "leaflet-bar");
        const a = L.DomUtil.create("a", "", bar);
        a.href = "#";
        a.title = "Centra sulla casa";
        a.setAttribute("role", "button");
        a.innerHTML = '<ha-icon icon="mdi:home-map-marker"></ha-icon>';
        L.DomEvent.disableClickPropagation(bar);
        L.DomEvent.on(a, "click", (ev) => {
          L.DomEvent.preventDefault(ev);
          this._recenter();
        });
        return bar;
      },
    });
    new HomeControl().addTo(this._map);
    L.marker(data.center, {
      icon: L.divIcon({ className: "", html: '<div class="home"></div>', iconSize: [12, 12] }),
      interactive: false,
      keyboard: false,
    }).addTo(this._map);
    this._overlay = L.imageOverlay("data:image/gif;base64,R0lGODlhAQABAAAAACw=", data.bounds, {
      opacity: 0.85,
      interactive: false,
      attribution: data.attribution,
    }).addTo(this._map);
  }

  _recenter() {
    const zoom = Math.max(this._config.zoom, this._map.getMinZoom());
    this._map.setView(this._center, zoom);
  }

  // Keep the view inside the area the radar images cover: no zooming out
  // or panning past their edges.
  _limitView() {
    const size = this._map.getSize();
    if (!size.x || !size.y) return;
    const min = this._map.getBoundsZoom(this._area, true);
    this._map.setMaxBounds(this._area);
    this._map.setMinZoom(min);
    if (this._map.getZoom() < min) this._map.setZoom(min);
    this._map.panInsideBounds(this._area, { animate: false });
  }

  _setBasemap(dark) {
    this._dark = dark;
    this._el.map.classList.toggle("dark", dark);
    if (this._base) return;
    const custom = this._config.tile_url;
    this._base = window.L.tileLayer(custom || BASEMAP, {
      maxZoom: 12,
      attribution: custom ? this._config.tile_attribution || "" : MAP_ATTRIBUTION,
    }).addTo(this._map);
    this._base.bringToBack();
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    clearTimeout(this._retryTimer);
    try {
      const data = await withTimeout(this._hass.callApi("GET", `radar_pioggia/frames/${this._config.entity}`));
      await this._initMap(data);
      this._area = window.L.latLngBounds(data.bounds);
      this._overlay.setBounds(this._area);
      this._limitView();
      const wasLast = this._index >= this._nowIndex();
      const images = new Map();
      for (const f of data.frames) {
        images.set(f.url, this._images.get(f.url) || (await this._fetchImage(f.url)));
      }
      for (const [url, obj] of this._images) if (!images.has(url)) URL.revokeObjectURL(obj);
      this._images = images;
      this._frames = data.frames.map((f) => ({ ...f, date: new Date(f.time), img: images.get(f.url) }));
      this._el.range.max = String(Math.max(0, this._frames.length - 1));
      this._el.msg.textContent = this._frames.length ? "" : "Nessun dato radar";
      this._retried = false;
      this._fails = 0;
      if (!this._playing) this._show(wasLast || this._index >= this._frames.length ? this._nowIndex() : this._index);
    } catch (err) {
      // The frame list changed while loading the images: read it once more.
      if (err && err.status === 409 && !this._retried) {
        this._retried = true;
        this._loading = false;
        return this._load();
      }
      // Keep showing the frames already loaded, and try again shortly.
      if (!this._frames.length) this._el.msg.textContent = "Radar non disponibile, riprovo…";
      const fails = this._fails || 0;
      this._fails = fails + 1;
      this._retryTimer = setTimeout(() => this._load(), RETRY_MS[Math.min(fails, RETRY_MS.length - 1)]);
      console.warn("radar-pioggia-card:", err);
    } finally {
      this._loading = false;
    }
  }

  async _fetchImage(url) {
    const resp = await withTimeout(this._hass.fetchWithAuth(url));
    if (!resp.ok) throw Object.assign(new Error(`HTTP ${resp.status}`), { status: resp.status });
    return URL.createObjectURL(await resp.blob());
  }

  // Index of the newest measured frame ("now").
  _nowIndex() {
    let i = 0;
    this._frames.forEach((f, k) => { if (!f.forecast) i = k; });
    return i;
  }

  _show(i) {
    const f = this._frames[i];
    if (!f) return;
    this._index = i;
    this._el.range.value = String(i);
    this._overlay.setUrl(f.img);
    this._overlay.setOpacity(f.forecast ? 0.7 : 0.85);
    const now = this._frames[this._nowIndex()].date;
    const diff = Math.round((f.date - now) / 60000);
    let text;
    if (f.forecast) text = `${hhmm(f.date)} · +${diff}′`;
    else if (diff === 0) text = `${hhmm(f.date)} · ora`;
    else text = `${hhmm(f.date)} · −${-diff}′`;
    this._el.when.textContent = text;
    this._el.when.classList.toggle("forecast", !!f.forecast);
    this._el.when.title = f.forecast ? "Previsione: radar attuale spostato secondo il movimento misurato" : "Radar misurato";
  }

  _play() {
    if (!this._frames.length) return;
    this._playing = true;
    this._el.icon.setAttribute("icon", "mdi:pause");
    const tick = () => {
      if (!this._playing) return;
      const last = this._index >= this._frames.length - 1;
      this._show(last ? 0 : this._index + 1);
      this._tick = setTimeout(tick, this._index >= this._frames.length - 1 ? HOLD_MS : STEP_MS);
    };
    tick();
  }

  _stop() {
    this._playing = false;
    clearTimeout(this._tick);
    if (this._el) this._el.icon.setAttribute("icon", "mdi:play");
  }
}

// A page still open across an update can load the card a second time.
if (!customElements.get("radar-pioggia-card")) {
  customElements.define("radar-pioggia-card", RadarPioggiaCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "radar-pioggia-card",
    name: "Radar pioggia",
    description: "Mappa del radar con l'ultima ora e la stima della prossima, con cursore del tempo.",
    preview: true,
  });
}

// Visual editor.
const EDITOR_SCHEMA = [
  { name: "entity", required: true, selector: { entity: { filter: { integration: "radar_pioggia" } } } },
  { name: "title", selector: { text: {} } },
  {
    type: "grid",
    name: "",
    schema: [
      { name: "icon", selector: { icon: {} } },
      { name: "color", selector: { ui_color: { include_none: true } } },
    ],
  },
  { name: "zoom", selector: { number: { min: 5, max: 12, step: 0.25, mode: "box" } } },
  { name: "bare", selector: { boolean: {} } },
  { name: "tile_url", selector: { text: {} } },
  { name: "tile_attribution", selector: { text: {} } },
];
const EDITOR_LABELS = {
  entity: "Punto (un'entità di Radar pioggia)",
  title: "Titolo (vuoto = nessuna intestazione)",
  icon: "Icona del titolo",
  color: "Colore dell'icona e dello sfondo",
  zoom: "Zoom iniziale",
  bare: "Senza sfondo (dentro un'altra scheda)",
  tile_url: "Mappa di sfondo: indirizzo dei tile (vuoto = OpenStreetMap)",
  tile_attribution: "Mappa di sfondo: crediti da mostrare",
};

class RadarPioggiaCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => EDITOR_LABELS[s.name] ?? s.name;
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...ev.detail.value };
        for (const k of Object.keys(config)) if (config[k] === "" || config[k] === undefined) delete config[k];
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { zoom: 8, ...this._config };
    this._form.schema = EDITOR_SCHEMA;
  }
}

if (!customElements.get("radar-pioggia-card-editor")) customElements.define("radar-pioggia-card-editor", RadarPioggiaCardEditor);
