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
Anything older than 72 hours is filtered out.

## Documents

The documents page automatically reads PDF files from `documents/files/`.
Add or rename a PDF there, and the page updates with the new file list.

## Earthquakes

The earthquake dashboard shows live USGS data and includes recent feed options,
including major earthquakes from the last 72 hours.

## RSS notes

`OnlyNews.py` is a small RSS-to-Obsidian note generator.

- add your feed URLs at the top of `OnlyNews.py`
- run it to create article notes in your chosen output folder
- each note links back to `Dashboard Hub`, `Documents`, and `Earthquakes`
- source notes are created alongside the articles so everything stays linked

The homepage notification bell shows:

- recent major earthquakes from the USGS feed
- document collection updates from `documents/files/`
- future site updates when they are added

Notifications can be dismissed individually or cleared all at once, and nothing
is shown when there are no recent updates.

## Shared link

Use this page as the main entry point:

https://remkopape.github.io/dashboard-hub/
