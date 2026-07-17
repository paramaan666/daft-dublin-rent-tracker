# Dublin Rent Tracker — Daft.ie + Rent.ie

Automatický tracker nájmů v Dublinu, který spojuje:

- **Daft.ie Saved Search + Gmail alerty**
- **Rent.ie veřejný RSS feed**
- ruční seed CSV
- GitHub Actions a GitHub Pages

Projekt neprochází detailní stránky jako hromadný crawler. Daft.ie data čte z emailových alertů a Rent.ie data z RSS odkazu, který Rent.ie nabízí na stránce výsledků vyhledávání. Metadata a URL obrázků se ukládají do společného datasetu; obrázky se nekopírují ani nerehostují.

## Společné filtry

Výchozí konfigurace v `config.example.yaml`:

- lokality: Dublin 1, 2, 4, 6, 7, 8, 9, 10, 12, 14, 16
- maximální nájem: 1600 EUR za měsíc
- minimum: 1 double bed, pokud je údaj ve zdroji rozpoznatelný

Týdenní cena se pro kontrolu limitu přepočítává na měsíční ekvivalent `weekly × 52 / 12`.

Když zdroj neobsahuje postcode nebo typ postele, nabídka může zůstat v datasetu s `needs_review=true`. Jasné texty jako `single occupancy`, `one person only`, `no couples` nebo `single room` se odmítnou.

## Zdroje

### Daft.ie

Vytvoř na Daft.ie Saved Search se stejnými filtry a zapni emailové alerty. Gmail query je ve výchozím nastavení připravená pro zprávy z Daft.ie i Rent.ie.

### Rent.ie

Rent.ie RSS je zapnuté automaticky:

```yaml
rent_ie_enabled: true
rent_ie_feed_urls:
  - https://rss.rent.ie/houses-to-let/renting_dublin/
```

Lze přidat více RSS URL. Každý feed se načte samostatně; chyba jednoho feedu nezastaví import seedů ani Gmail alertů.

## Co se publikuje

Po každém běhu vzniknou:

- `data/listings.json`
- `data/listings.csv`
- `data/events.jsonl`
- `site/index.html`

Web zobrazuje Daft.ie a Rent.ie v jednom seznamu, přidává badge zdroje a umožňuje filtrovat jen jeden portál.

Veřejná stránka:

```text
https://paramaan666.github.io/daft-dublin-rent-tracker/
```

## Setup

```bash
cp config.example.yaml config.yaml
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -e ".[dev]"
python -m pytest -q
python -m daft_tracker --config config.yaml --data-dir data --site-dir site update
python -m http.server 8000 --directory site
```

### Gmail OAuth

Pro import alertů jsou potřeba GitHub Actions secrets:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`

Refresh token lze vytvořit:

```bash
python scripts/get_google_refresh_token.py --client-secret client_secret.json
```

Bez Gmail credentials se Gmail import přeskočí, ale Rent.ie RSS a seed CSV dál fungují.

## Ruční seed

`seeds/listings_seed.csv` podporuje Daft.ie i Rent.ie URL. ID může zůstat prázdné, pokud URL končí číselným ID inzerátu; doplní se prefix `daft-` nebo `rentie-`.

## Datový model

Důležitá pole:

- `id`
- `source`
- `status`
- `needs_review`
- `review_reasons`
- `title`
- `location`
- `postcode`
- `price_eur`
- `rent_period`
- `double_beds`
- `url`
- `thumbnail_url`
- `image_urls`
- `first_seen`
- `last_seen`
- `price_history`
- `change_history`

## Omezení

RSS zpravidla obsahuje jen nejnovější položky a nemusí obsahovat všechny detaily. Zmizelý inzerát nelze bez stavového API potvrdit okamžitě; po `stale_after_days` dostane stav `possibly_removed`.

## Bezpečnost a práva

- Necommituj Gmail tokeny ani OAuth secrets.
- Nerehostuj obrázky; ukládají se pouze jejich veřejné URL.
- Při změně podmínek portálů ověř, že způsob použití jejich alertů a RSS zůstává povolený.
