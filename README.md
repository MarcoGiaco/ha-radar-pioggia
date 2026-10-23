# Radar pioggia per Home Assistant

Integrazione custom che legge il radar meteo della [Protezione Civile (Radar-DPC)](https://radar.protezionecivile.it) — con [RainViewer](https://www.rainviewer.com) come riserva fuori dall'Italia — e dice se la pioggia sta arrivando su un punto (di default casa tua): a che distanza è, da dove arriva, a che velocità e tra quanti minuti è prevista.

> **Progetto non ufficiale**, non affiliato al Dipartimento della Protezione Civile né a RainViewer.
>
> - **Radar-DPC**: mosaico radar nazionale, un fotogramma ogni 5 minuti, valori in dBZ (prodotto VMI), circa 1 km per pixel. Dati con licenza [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/): la fonte va citata.
> - **RainViewer**: API pubblica gratuita, un fotogramma ogni 10 minuti, intensità ricostruita dai colori della mappa. Secondo i [termini di RainViewer](https://www.rainviewer.com/api.html) l'API è **solo per uso personale ed educativo**, citando RainViewer: non usare questa integrazione per scopi commerciali con RainViewer come fonte.
> - **Mappa di sfondo** della scheda e dell'entità *Mappa radar*: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, dati con licenza [ODbL](https://opendatacommons.org/licenses/odbl/), secondo la loro [policy sull'uso dei tile](https://operations.osmfoundation.org/policies/tiles/). Nelle opzioni si può scegliere anche OpenTopoMap (vedi *Mappa di sfondo*): in quel caso valgono i suoi termini.
>
> I dati non passano da nessun server di questo progetto: ogni installazione di Home Assistant li scarica direttamente dalle fonti.
>
> Le entità riportano la fonte; l'attributo `fonte` di *Ora radar* dice quale è stata usata.

Alla configurazione il punto parte dalla posizione di casa impostata in Home Assistant. Se la posizione non è stata impostata (è ancora quella predefinita), l'integrazione lo segnala e non accetta quel punto.

## Come funziona

1. Controlla se c'è un fotogramma nuovo e scarica le tessere radar attorno al punto (raggio configurabile, 60 km di default, più un margine di circa 165 km: la strada che la pioggia più veloce considerata, 110 km/h, fa in 90 minuti; serve alla stima del movimento, alla previsione della mappa e al calcolo dell'arrivo; sono circa 9 tessere per fotogramma). Prova prima Radar-DPC; se non risponde o il punto è fuori copertura usa RainViewer. DPC pubblica un fotogramma ogni 5 minuti, circa 8 minuti dopo l'orario del radar: l'integrazione impara questo ritardo e, quando il fotogramma sta per uscire, controlla ogni 30 secondi, così lo usa al massimo mezzo minuto dopo la pubblicazione. Con RainViewer controlla ogni 5 minuti.
2. Trova la pioggia più vicina, la più forte e quella sopra il punto, ignorando i pixel isolati.
3. Confronta il fotogramma attuale con quello di 20 minuti prima, su tutta l'area scaricata, per stimare direzione e velocità di spostamento: così il movimento si conosce anche quando la pioggia è ancora tutta fuori dal raggio.
4. Sposta in avanti la mappa attuale a passi di 5 minuti, fino a 90, e calcola quando la pioggia arriva entro la *distanza di arrivo* dal punto (3 km di default).

È un *nowcast* per spostamento: funziona bene con fronti e temporali che si muovono. Non può prevedere le celle che nascono sul posto, e nelle valli il radar può vedere male i rovesci piccoli.

## Entità

| Entità | Contenuto |
|---|---|
| Pioggia sul punto | mm/h stimati sopra il punto adesso (0 se asciutto) |
| Distanza pioggia | km della pioggia più vicina, con direzione e intensità |
| Arrivo pioggia | minuti all'arrivo stimato (0 se la pioggia è già entro la distanza di arrivo, vuoto se non arriva entro 90 min) |
| Velocità pioggia | km/h di spostamento, con la direzione di provenienza |
| Pioggia più forte | mm/h della cella più intensa nel raggio, con distanza e direzione |
| Ora radar | ora del fotogramma analizzato (attributo `fonte`: Radar-DPC o RainViewer) |
| Pioggia in arrivo | acceso quando l'arrivo stimato è entro il preavviso (45 min di default) |
| Temporale vicino | acceso quando c'è una cella ≥ 45 dBZ entro 30 km |
| Mappa radar | immagine PNG dell'ultimo fotogramma radar sopra la mappa, con il punto in rosso (vedi *Immagine mappa*) |

Intensità da dBZ con Marshall-Palmer (Z = 200·R^1,6): 20 dBZ ≈ 0,6 mm/h, 30 ≈ 2,7, 40 ≈ 11,5, 45 ≈ 24, 50 ≈ 49.

## Opzioni

Da **Impostazioni → Dispositivi e servizi → Radar pioggia → Configura**:

| Opzione | Default | Cosa cambia |
|---|---|---|
| Raggio analizzato | 60 km (20–150) | area per distanza, pioggia più forte, temporale vicino e mappa |
| Preavviso | 45 min (15–90) | quando si accende *Pioggia in arrivo* |
| Distanza di arrivo | 3 km (1–30) | entro quanti km dal punto la pioggia conta come arrivata, per *Arrivo pioggia* e *Pioggia in arrivo*. *Pioggia sul punto* guarda sempre i 3 km attorno al punto |
| Nascondi le eco deboli sulla mappa | no | non colora le eco sotto i 15 dBZ (pioviggine o pioggia che evapora prima di arrivare a terra), nella scheda e nell'immagine *Mappa radar*. Sensori e avvisi non cambiano |
| Mappa di sfondo | OpenStreetMap | lo sfondo dell'immagine *Mappa radar* e della scheda, vedi *Mappa di sfondo* |

### Mappa di sfondo

Nelle opzioni si sceglie lo sfondo tra:

| Mappa | Fornitore | Crediti mostrati |
|---|---|---|
| OpenStreetMap | [OpenStreetMap](https://www.openstreetmap.org/copyright) ([policy dei tile](https://operations.osmfoundation.org/policies/tiles/)) | © OpenStreetMap |
| Topografica | [OpenTopoMap](https://opentopomap.org/about), con i rilievi | © OpenStreetMap, SRTM · © OpenTopoMap (CC BY-SA) |

I crediti compaiono da soli sotto la mappa della scheda e nella didascalia dell'immagine. Una scheda con il suo `tile_url` usa invece quello (vedi *Scheda*).

## Installazione

**Con HACS:** HACS → menu ⋮ → *Repository personalizzati* → aggiungi `https://github.com/MarcoGiaco/ha-radar-pioggia` come tipo *Integrazione*, poi installa *Radar pioggia*.

**A mano:** copia `custom_components/radar_pioggia` in `config/custom_components/`.

In entrambi i casi riavvia Home Assistant, poi **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → Radar pioggia**.

## Scheda mappa

L'integrazione porta con sé una scheda (`custom:radar-pioggia-card`), caricata in automatico: l'integrazione la aggiunge da sola alle risorse delle dashboard (Impostazioni → Dashboard → Risorse) e ne aggiorna la versione. Non serve aggiungerla a mano, e quando elimini l'ultimo punto configurato la risorsa viene tolta. Se invece disinstalli solo da HACS senza prima eliminare l'integrazione, la risorsa resta e va tolta a mano. La scheda mostra:
- il radar dell'ultima ora, un fotogramma ogni 5 minuti con DPC;
- la stima della prossima ora, con l'ultimo fotogramma spostato secondo il movimento misurato. La stima compare solo quando c'è pioggia che si muove;
- un cursore per scorrere il tempo e un tasto play.

Si aggiunge da **Aggiungi scheda → Radar pioggia**: l'entità del radar viene scelta in automatico e tutte le opzioni si cambiano dall'editor visuale. In YAML:

```yaml
type: custom:radar-pioggia-card
entity: sensor.radar_pioggia_casa_ora_radar   # una qualsiasi entità del punto
title: Radar                                  # facoltativo; senza titolo niente intestazione
icon: mdi:radar                               # icona del titolo
color: red                                    # facoltativo: nome di un colore del tema, "#e57373" o "var(--…)"
zoom: 8                                       # zoom iniziale
bare: false                                   # true = senza sfondo, per metterla dentro un'altra scheda
tile_url: https://…/{z}/{x}/{y}.png           # facoltativo: altra mappa di sfondo
tile_attribution: "© …"                       # crediti richiesti da quella mappa
```

Senza `color` la scheda ha lo sfondo normale del tema. Con `color` l'icona prende quel colore e lo sfondo una leggera sfumatura. Mappa, cursore e pulsanti seguono sempre il tema, chiaro o scuro. Per altri ritocchi (angoli, margini) si può usare card-mod, per esempio:

```yaml
card_mod:
  style: "ha-card { padding: 18px 20px !important; border-radius: 20px !important; }"
```

La mappa resta dentro l'area scaricata: non si può allontanare né spostare oltre i bordi dell'immagine radar. Il pulsante con la casa la riporta sul punto.

Le immagini sono preparate da Home Assistant: i tile DPC non si possono leggere direttamente dal browser. Lo sfondo è quello scelto nelle opzioni dell'integrazione (di serie OpenStreetMap), scurito in tema scuro. Con `tile_url` una singola scheda può usare un altro fornitore (formato `{z}/{x}/{y}`): in quel caso metti in `tile_attribution` i crediti che il fornitore richiede e rispetta i suoi termini.

## Immagine mappa

L'entità *Mappa radar* (`image.radar_pioggia_casa_mappa_radar`) è una foto di circa 570×570 px: l'ultimo fotogramma radar sopra la mappa di sfondo (di serie OpenStreetMap), con il punto segnato in rosso e in basso ora, fonte e crediti della mappa. Si aggiorna a ogni fotogramma nuovo. Serve soprattutto per le notifiche, ma si può mostrare anche con una normale scheda *Immagine*.

La mappa di sfondo (una decina di tile) viene scaricata solo la prima volta che l'immagine viene chiesta, poi resta in memoria fino al riavvio. Se l'immagine non viene mai usata, non si scarica nulla. L'immagine col radar viene disegnata una volta per fotogramma.

## Esempio di notifica

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.radar_pioggia_casa_pioggia_in_arrivo
    to: "on"
actions:
  - action: notify.send_message
    target:
      entity_id: notify.telegram
    data:
      message: >-
        🌧️ Pioggia {{ state_attr(trigger.entity_id, 'intensita') }} in arrivo da
        {{ state_attr(trigger.entity_id, 'provenienza') }}
        tra circa {{ state_attr(trigger.entity_id, 'minuti') }} minuti.
```

Con la foto della mappa, per esempio con Telegram. Home Assistant scarica l'immagine da se stesso: l'indirizzo è quello interno della tua installazione (qui `http://127.0.0.1:8123`, se non usi HTTPS), e il token nell'attributo `entity_picture` cambia da solo.

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

## Licenza

Il codice è MIT, vedi [LICENSE](LICENSE). I dati radar e le mappe restano soggetti alle licenze e ai termini delle rispettive fonti, elencati in cima.
