# Dashboard Hub

A compact GitHub Pages site with a few useful web pages:

- `index.html` — the main hub and overview
- `documents/` — a shareable document page for CVs, certificates, and PDFs
- `earthquakes/` — a live USGS earthquake map and alert view

## What it’s for

This repo is meant to be easy to share and easy to embed in Obsidian. The
homepage stays small and readable, while the documents page is the main public
sharing link.

The homepage includes a compact readme/about section plus a notification bell
for recent earthquake alerts and document updates from the last 72 hours.

## Documents

The documents page automatically reads PDF files from `documents/files/`.
Add or rename a PDF there, and the page updates with the new file list.

## Earthquakes

The earthquake dashboard shows live USGS data and includes recent feed options,
including major earthquakes from the last 72 hours.

The homepage notification bell shows:

- recent major earthquakes from the USGS feed
- document collection updates from `documents/files/`
- a placeholder slot for future site updates

## Shared link

Use this page as the main entry point:

https://remkopape.github.io/dashboard-hub/
