# Manual seed notes — 2026-07-09

This seed was created from a one-off manual pass over publicly visible Daft pages and detail pages for the configured Dublin areas.

Configured target:
- Dublin 1, 2, 4, 6, 7, 8, 9, 10, 12, 14, 16
- Maximum monthly rent: €1,500
- Target bed requirement: at least one double/manželská bed where visible

How to read the dataset:
- `needs_review = false`: stronger match from a detail page, within price cap, with one-bed/double-bedroom evidence.
- `needs_review = true`: candidate should be checked before acting, usually because it is a studio, house-share/room-share, short-term only, single bedroom, or the detail page could not be fetched during the manual pass.
- Photos are intentionally left empty. The tracker should not re-host Daft photos; use the Daft listing link.

Main files updated:
- `data/listings.json`
- `data/listings.csv`
- `site/data/listings.json`
- `site/data/listings.csv`
- `seeds/listings_seed.csv`

Audit file:
- `seeds/visible_daft_candidates_review.csv`

Important limitation:
This is not a complete crawler of all Daft results. It is a manual bootstrap seed. From now on, the scheduled Gmail/Daft alert workflow should keep adding new listings as alert emails arrive.
