# Dashboard Hub

A compact GitHub Pages site with a few useful web pages:

- `index.html` - the main hub and overview
- `documents/` - a shareable document page for CVs, certificates, and PDFs
- `earthquakes/` - a live USGS earthquake map and alert view
- `wildfires/` - a live NASA FIRMS wildfire map
- `news/` - a selected RSS feed page with a browser-side reader

## What it is for

This repo is meant to be easy to share and easy to embed in Obsidian. The
homepage stays small and readable, while the documents page is the main public
sharing link.

The homepage includes a compact readme/about section, a notification bell for
recent earthquakes, document updates, and RSS updates from the last 72 hours,
plus a compact latest-news preview.

## Environment setup

This repo now supports a root `.env` file for the local Python scripts.

1. Copy `.env.example` to `.env`
2. Fill in the values you want to use

Available variables:

- `ONLYNEWS_OUTPUT_DIR` - optional override for `OnlyNews.py` output folder
- `ONLYNEWS_LIMIT_PER_FEED` - optional override for how many feed items `OnlyNews.py` reads per source

Example:

```env
ONLYNEWS_OUTPUT_DIR=news
ONLYNEWS_LIMIT_PER_FEED=8
```

## Wildfire data

The wildfire page now fetches NASA FIRMS directly in the browser with a public
key defined in `wildfires/config.js`.

This means:

- no local wildfire snapshot files are required for the page to work
- the FIRMS key is public in the frontend
- the page uses live 24h, 3d, and 5d views instead of repository snapshots

## Documents

The documents page automatically reads PDF files from `documents/files/`.
Add or rename a PDF there, and the page updates with the new file list.

## Earthquakes

The earthquake dashboard shows live USGS data and includes recent feed options,
including major earthquakes from the last 72 hours.

## RSS Notes

The selected feed list lives in `news/feeds.js`.

- the `news/` page reads those selected sources directly in the browser
- the homepage preview and notification bell use the same shared feed loader
- feed requests use browser-readable JSON first, then an XML proxy fallback
- `OnlyNews.py` can still exist for local note work, but the public feed no longer depends on it

## Notifications

The homepage notification bell shows:

- recent major earthquakes from the USGS feed
- document collection updates from `documents/files/`
- recent RSS items from the shared browser-side news loader

Notifications can be dismissed individually or cleared all at once, and nothing
is shown when there are no recent updates.

## Shared link

Use this page as the main entry point:

https://remkopape.github.io/dashboard-hub/
