# Radar pioggia per Home Assistant

Integrazione per Home Assistant che avvisa quando la pioggia sta per arrivare su un punto scelto, di solito la casa. Indica a che distanza è la pioggia, da dove arriva, a che velocità si muove e tra quanti minuti è attesa.

I dati vengono dal radar meteo della [Protezione Civile (Radar-DPC)](https://radar.protezionecivile.it). Fuori dall'Italia, o quando il radar DPC non risponde, viene usato [RainViewer](https://www.rainviewer.com).

Oltre ai sensori, l'integrazione include:

- una **scheda mappa** con il radar dell'ultima ora e la stima della prossima;
- un'**immagine** dell'ultimo fotogramma radar, pronta da allegare alle notifiche.

> **Progetto non ufficiale**, non affiliato al Dipartimento della Protezione Civile né a RainViewer. Fonti e licenze dei dati sono in fondo, in *Fonti dei dati*.

## Installazione

**Con HACS:** HACS → menu ⋮ → *Repository personalizzati* → aggiungere `https://github.com/MarcoGiaco/ha-radar-pioggia` come tipo *Integrazione*, poi installare *Radar pioggia*.

**A mano:** copiare la cartella `custom_components/radar_pioggia` in `config/custom_components/`.

Poi riavviare Home Assistant e aggiungere l'integrazione da **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Radar pioggia**.

Durante la configurazione si sceglie un nome e il punto da sorvegliare. Il punto proposto è la posizione di casa impostata in Home Assistant. Se quella posizione è ancora quella predefinita, l'integrazione non la accetta: basta spostare il punto sulla mappa, oppure impostare la posizione in *Impostazioni → Sistema → Generale*. Si possono aggiungere più punti, uno per volta.

## Entità

Gli ID delle entità contengono il nome del punto. Per un punto chiamato "Casa": `sensor.radar_pioggia_casa_arrivo_pioggia`, `binary_sensor.radar_pioggia_casa_pioggia_in_arrivo` e così via.

| Entità | Cosa indica |
|---|---|
| Pioggia sul punto | mm/h stimati sopra il punto in questo momento (0 se asciutto) |
| Distanza pioggia | km della pioggia più vicina, con direzione e intensità |
| Arrivo pioggia | minuti all'arrivo stimato: 0 se la pioggia è già arrivata, vuoto se non è attesa entro 90 minuti |
| Velocità pioggia | km/h di spostamento della pioggia e direzione di provenienza |
| Pioggia più forte | mm/h della cella più intensa nell'area, con distanza e direzione |
| Ora radar | ora del fotogramma analizzato; l'attributo `fonte` dice se viene da Radar-DPC o da RainViewer |
| Pioggia in arrivo | acceso quando la pioggia è attesa entro il preavviso (45 minuti di serie) |
| Temporale vicino | acceso quando c'è una cella forte (≥ 45 dBZ) entro 30 km |
| Mappa radar | immagine dell'ultimo fotogramma radar sopra la mappa, con il punto in rosso |

Le entità hanno attributi utili per le notifiche, per esempio `minuti`, `ora`, `intensita` (debole, moderata, forte…), `mm_h`, `provenienza` e `velocita_kmh` su *Pioggia in arrivo* e *Arrivo pioggia*.

L'intensità in mm/h si ricava dai dBZ del radar con la formula di Marshall-Palmer (Z = 200·R^1,6): 20 dBZ ≈ 0,6 mm/h, 30 ≈ 2,7, 40 ≈ 11,5, 45 ≈ 24, 50 ≈ 49.

## Opzioni

Da **Impostazioni → Dispositivi e servizi → Radar pioggia → Configura**:

| Opzione | Valore di serie | A cosa serve |
|---|---|---|
| Raggio analizzato | 60 km (20–150) | area usata per distanza, pioggia più forte, temporale vicino e mappa |
| Preavviso | 45 min (15–90) | quanto prima dell'arrivo si accende *Pioggia in arrivo* |
| Distanza di arrivo | 3 km (1–30) | entro quanti km dal punto la pioggia conta come arrivata (per *Arrivo pioggia* e *Pioggia in arrivo*). *Pioggia sul punto* guarda sempre i 3 km attorno al punto |
| Nascondi le eco deboli sulla mappa | no | non colora sulla mappa le eco sotto i 15 dBZ (pioviggine, o pioggia che evapora prima di toccare terra). Sensori e avvisi non cambiano |
| Mappa di sfondo | OpenStreetMap | sfondo della scheda e dell'immagine *Mappa radar* |

### Mappa di sfondo

| Mappa | Fornitore | Crediti mostrati |
|---|---|---|
| OpenStreetMap | [OpenStreetMap](https://www.openstreetmap.org/copyright) | © OpenStreetMap |
| Topografica (con i rilievi) | [OpenTopoMap](https://opentopomap.org/about) | © OpenStreetMap, SRTM · © OpenTopoMap (CC BY-SA) |

I crediti compaiono da soli sotto la mappa della scheda e nella didascalia dell'immagine.

## Scheda mappa

La scheda (`custom:radar-pioggia-card`) viene installata con l'integrazione e aggiunta da sola alle risorse delle dashboard: non serve registrarla a mano. Mostra:

- il radar dell'ultima ora, un fotogramma ogni 5 minuti;
- la stima della prossima ora, ottenuta spostando l'ultimo fotogramma secondo il movimento misurato (compare solo quando c'è pioggia in movimento);
- un cursore per scorrere il tempo, un tasto play e un tasto per tornare sul punto.

Si aggiunge da **Aggiungi scheda → Radar pioggia**: l'entità viene scelta in automatico e le opzioni si cambiano dall'editor visuale. In YAML:

```yaml
type: custom:radar-pioggia-card
entity: sensor.radar_pioggia_casa_ora_radar   # una qualsiasi entità del punto
title: Radar                                  # facoltativo; senza titolo niente intestazione
icon: mdi:radar                               # icona del titolo
color: red                                    # facoltativo: colore del tema, "#e57373" o "var(--…)"
zoom: 8                                       # zoom iniziale
bare: false                                   # true = senza sfondo, per inserirla in un'altra scheda
tile_url: https://…/{z}/{x}/{y}.png           # facoltativo: un'altra mappa di sfondo
tile_attribution: "© …"                       # crediti richiesti da quella mappa
```

Note:

- Senza `color` la scheda ha lo sfondo normale del tema; con `color` l'icona prende quel colore e lo sfondo una leggera sfumatura. Mappa e comandi seguono il tema chiaro o scuro.
- La mappa resta dentro l'area scaricata dal radar: non si può spostare oltre i bordi.
- Con `tile_url` si può usare un altro fornitore di mappe solo per quella scheda: i crediti vanno messi in `tile_attribution` e vanno rispettati i termini del fornitore.
- Per ritocchi grafici (angoli, margini) si può usare card-mod:

  ```yaml
  card_mod:
    style: "ha-card { padding: 18px 20px !important; border-radius: 20px !important; }"
  ```

- Se l'integrazione viene disinstallata da HACS senza prima eliminare i punti configurati, la scheda resta tra le risorse delle dashboard e va tolta a mano.

## Immagine mappa

L'entità *Mappa radar* (es. `image.radar_pioggia_casa_mappa_radar`) è un'immagine di circa 570×570 px: l'ultimo fotogramma radar sopra la mappa di sfondo, con il punto in rosso e, in basso, ora, fonte e crediti. Si aggiorna a ogni nuovo fotogramma. Serve soprattutto per allegare la mappa alle notifiche, ma si può mostrare anche con una normale scheda *Immagine*.

La mappa di sfondo viene scaricata solo la prima volta che l'immagine viene richiesta; se l'immagine non si usa, non si scarica nulla.

## Esempi di automazione

Notifica quando la pioggia è in arrivo (sostituire `notify.telefono` con il proprio servizio di notifica):

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.radar_pioggia_casa_pioggia_in_arrivo
    to: "on"
actions:
  - action: notify.send_message
    target:
      entity_id: notify.telefono
    data:
      message: >-
        🌧️ Pioggia {{ state_attr(trigger.entity_id, 'intensita') }} in arrivo da
        {{ state_attr(trigger.entity_id, 'provenienza') }}
        tra circa {{ state_attr(trigger.entity_id, 'minuti') }} minuti.
```

Con la foto della mappa, per esempio su Telegram. Home Assistant scarica l'immagine da se stesso: l'indirizzo va adattato alla propria installazione (`http://127.0.0.1:8123` vale se HA non usa HTTPS). Il token contenuto in `entity_picture` si rinnova da solo.

```yaml
actions:
  - action: telegram_bot.send_photo
    data:
      url: >-
        {{ 'http://127.0.0.1:8123' ~
           state_attr('image.radar_pioggia_casa_mappa_radar', 'entity_picture') }}
      caption: >-
        🌧️ Pioggia in arrivo tra circa
        {{ state_attr('binary_sensor.radar_pioggia_casa_pioggia_in_arrivo', 'minuti') }} minuti.
```

## Come funziona

1. **Scarica il radar** attorno al punto. Radar-DPC pubblica un fotogramma ogni 5 minuti, circa 8 minuti dopo l'orario della misura: l'integrazione impara questo ritardo e usa ogni fotogramma entro mezzo minuto dalla pubblicazione. Con RainViewer controlla ogni 5 minuti. Oltre al raggio scelto scarica un margine più ampio, così può seguire la pioggia anche prima che entri nell'area.
2. **Cerca la pioggia**: la più vicina, la più forte e quella sopra il punto, ignorando i pixel isolati.
3. **Misura il movimento** confrontando il fotogramma attuale con quello di 20 minuti prima: ne ricava direzione e velocità.
4. **Stima l'arrivo** spostando in avanti la pioggia attuale a passi di 5 minuti, fino a 90 minuti, finché non arriva entro la *distanza di arrivo* dal punto.

### Limiti

La stima segue la pioggia che già esiste e si sposta: funziona bene con fronti e temporali in movimento, ma non può prevedere le celle che nascono sul posto. Nelle valli, il radar può vedere male i rovesci piccoli.

## Fonti dei dati

- **Radar-DPC** (Protezione Civile): mosaico radar nazionale, un fotogramma ogni 5 minuti, risoluzione di circa 1 km. Dati con licenza [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/): la fonte va citata.
- **RainViewer**: API pubblica gratuita, un fotogramma ogni 10 minuti; l'intensità è ricavata dai colori della mappa. Secondo i [termini di RainViewer](https://www.rainviewer.com/api.html) l'API è **solo per uso personale ed educativo**, citando RainViewer: non va usata per scopi commerciali.
- **Mappe di sfondo**: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, licenza [ODbL](https://opendatacommons.org/licenses/odbl/), secondo la [policy sull'uso dei tile](https://operations.osmfoundation.org/policies/tiles/). Con la mappa topografica valgono anche i termini di [OpenTopoMap](https://opentopomap.org/about).

I dati non passano da server di questo progetto: ogni installazione di Home Assistant li scarica direttamente dalle fonti.

## Licenza

Il codice è distribuito con licenza MIT, vedi [LICENSE](LICENSE). La scheda della mappa include [Leaflet](https://leafletjs.com) 1.9.4 (licenza BSD-2-Clause, vedi [frontend/leaflet/LICENSE](custom_components/radar_pioggia/frontend/leaflet/LICENSE)), servito da Home Assistant stesso e non da internet. I dati radar e le mappe restano soggetti alle licenze e ai termini delle rispettive fonti, elencati in *Fonti dei dati*.
