# market-data

Daily US sector and industry relative-strength snapshot, built by a GitHub Action after the US close.

- `market.json`: the latest snapshot (sector and industry RS vs SPY, trend, distance from highs, basing tightness, macro readings, key ratios like ITB/SPY).
- `scripts/build_market_json.py`: builds it from Yahoo Finance daily closes.
- `.github/workflows/update.yml`: runs weekdays at 21:45 UTC; can also be run by hand from the Actions tab.

Read by the Thesis Board's daily ideas scan and the sector wall. Prices only; nothing personal.
