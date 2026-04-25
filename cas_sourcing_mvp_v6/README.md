# CAS Sourcing & Procurement Intelligence MVP v6

This build preserves the v1-v5 baseline and adds a stronger extraction layer for live supplier discovery.

## What changed in v6

- Keeps stable mock mode intact.
- Keeps v5 strict product-page discovery.
- Adds embedded-script / hydration-blob price extraction for pages where product data is present in inline JavaScript.
- Keeps CAS-confirmation safety gate so random prices from unrelated product/search pages are ignored.
- Deduplicates supplier/product rows for a cleaner UI.
- Improves the no-price diagnostic: no visible price can mean login-gated, JS-loaded, account-specific, or quote-only pricing.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Optional live discovery

Live discovery can use direct supplier pages only, or you can add a SerpAPI key in Streamlit secrets:

```toml
SERPAPI_KEY = "your_key_here"
```

## Important procurement rule

Visible catalog prices are evidence. Bulk prices are estimates. RFQ pricing is confirmed truth.
