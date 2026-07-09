# Daft Dublin Rent Tracker

Automatický tracker pro nájmy v Dublinu založený na **Daft Saved Search + Gmail alerts + GitHub Actions + GitHub Pages**.

Tento projekt záměrně **neprochází Daft.ie jako crawler**. Vstupem jsou emailové alerty, které Daft posílá k uloženému vyhledávání. Do veřejného datasetu se ukládají metadata a URL na fotky; fotky se nekopírují a nerehostují.

## Filtry

Výchozí konfigurace v `config.example.yaml` odpovídá zadání:

- lokality: Dublin 1, 2, 4, 6, 7, 8, 9, 10, 12, 14, 16
- max cena: 1500 EUR / měsíc
- minimum: 1 double bed / manželská postel, pokud je v emailu rozpoznatelná

Daft emaily někdy neobsahují všechny detaily. Když email neobsahuje postcode nebo typ postele, položka zůstane v datasetu s `needs_review=true`, protože primární filtr má být nastavený už v Daft Saved Search.

Nabídky, které jsou v emailu jasně označené jako `single room`, `single occupancy`, `one person only`, `no couples` nebo podobně, se zahodí automaticky.

## Co se publikuje

Po každém běhu vzniknou:

- `data/listings.json` — hlavní dataset
- `data/listings.csv` — tabulkový export
- `data/events.jsonl` — historie změn
- `site/index.html` — veřejná stránka pro GitHub Pages

Veřejná stránka po aktivaci GitHub Pages bude typicky na:

```text
https://<github-login>.github.io/<repo-name>/
```

Pro uživatele `paramaan666` a repo `daft-dublin-rent-tracker` tedy:

```text
https://paramaan666.github.io/daft-dublin-rent-tracker/
```

## Omezení bez Daft API

Bez oficiálního Daft API nebo povoleného crawleru nejde spolehlivě zjistit, že nabídka zmizela z Daftu. Tento projekt proto nedělá hromadné procházení webu. Stav `possibly_removed` nastaví až po `stale_after_days`, když už dlouho nepřišel žádný další signál k danému inzerátu.

Změnu ceny umí projekt zachytit tehdy, když přijde další alert/email se stejným Daft URL/ad ID a jinou cenou, nebo když cenu ručně upravíš v seed CSV.

## Setup

### 1. Vytvoř Daft Saved Search

Na Daft.ie ručně nastav vyhledávání podle zadání a zapni email alerts pro daný saved search. Doporučené filtry:

- Dublin 1, 2, 4, 6, 7, 8, 9, 10, 12, 14, 16
- max rent 1500 EUR / month
- rental/shared podle toho, co chceš sledovat
- double bed / 1 bed podle dostupnosti filtru na Daftu

### 2. Vytvoř GitHub repo

Doporučený název:

```text
daft-dublin-rent-tracker
```

Repo může být public, pokud má být dataset veřejný. Nahraj obsah tohoto projektu do repozitáře.

Pokud máš lokálně nainstalovaný GitHub CLI (`gh`), můžeš použít:

```bash
scripts/push_to_github.sh daft-dublin-rent-tracker public
```

### 3. Zkopíruj konfiguraci

```bash
cp config.example.yaml config.yaml
```

Uprav `config.yaml`, pokud budeš chtít jiné lokality, časový rozsah Gmail query nebo `stale_after_days`.

### 4. Přidej prvotní ruční seed

Do `seeds/listings_seed.csv` můžeš vložit aktuální nabídky, které ručně najdeš v Daftu. Formát:

```csv
id,url,title,location,postcode,price_eur,double_beds,thumbnail_url,first_seen,last_seen,status
daft-1234567,https://www.daft.ie/for-rent/apartment-test-dublin-8/1234567,Example flat,Dublin 8,Dublin 8,1450,1,https://example.com/image.jpg,2026-07-09T08:00:00+00:00,2026-07-09T08:00:00+00:00,active
```

`id` může zůstat prázdné, pokud URL končí číselným Daft ID; skript ho dopočítá.

### 5. Získej Gmail OAuth refresh token

Lokálně spusť:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/get_google_refresh_token.py --client-secret client_secret.json
```

`client_secret.json` je OAuth klient typu **Desktop app** z Google Cloud Console. Script vypíše tři hodnoty, které vložíš do GitHub Actions secrets:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`

Nikdy je necommituj do repozitáře.

### 6. Přidej GitHub Secrets

V GitHubu otevři:

```text
Settings → Secrets and variables → Actions → New repository secret
```

Přidej tři secrets z předchozího kroku.

### 7. Aktivuj GitHub Pages

V GitHubu otevři:

```text
Settings → Pages → Build and deployment → Source → GitHub Actions
```

Workflow `.github/workflows/update-and-publish.yml` potom stránku publikuje automaticky.

### 8. Spusť první běh

V GitHubu otevři:

```text
Actions → Update Daft tracker and publish Pages → Run workflow
```

Pak se workflow spustí automaticky každé ráno v 06:15 v timezone `Europe/Prague`.

## Lokální test

```bash
cp config.example.yaml config.yaml
pip install -r requirements.txt -e .
python -m daft_tracker --config config.yaml --data-dir data --site-dir site update
python -m http.server 8000 --directory site
```

Potom otevři:

```text
http://localhost:8000
```

## Datový model

Každá položka obsahuje hlavně:

- `id`
- `status`: `active` nebo `possibly_removed`
- `needs_review`
- `review_reasons`
- `title`
- `location`
- `postcode`
- `price_eur`
- `double_beds`
- `url`
- `thumbnail_url`
- `image_urls`
- `first_seen`
- `last_seen`
- `price_history`
- `change_history`

## Bezpečnost a práva

- Necommituj Gmail tokeny, Google client secrets ani jiné privátní credentials.
- Nerehostuj fotky z Daftu. Dataset uchovává pouze URL obrázků, pokud se objeví v alertu.
- Nepřidávej crawler Daft webu bez právního ověření a svolení.
