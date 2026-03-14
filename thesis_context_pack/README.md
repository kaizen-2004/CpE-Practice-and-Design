# Thesis context pack (Chapters 1–3)

This folder contains a Markdown export of your uploaded Word document (Chapters 1–3), split into **one Markdown file per section** (and sub-sections where applicable).

## Current status (updated 2026-03-04)

- Deployment now uses a split-host setup:
  - **Raspberry Pi 2** for local server hosting (dashboard/API/database/alerts).
  - **Second-hand laptop** for face recognition and fire detection processing.
- Monitoring scope remains **2 areas**: Living Room and Door Entrance Area.
- Sensor uplink remains **HTTP POST + JSON** to `POST /api/sensors/event`.

## Folder structure

- Each chapter has its own folder.
- Inside each chapter folder are section `.md` files.
- Chapter 2 and Chapter 3 include subfolders for sub-sections (e.g., Related Literatures topics; Data Gathering Instruments; Statistical Treatment).

## How to use in new AI sessions

Upload the whole folder (or the `.zip` version) and tell the AI to use it as context.  
If you only need a specific part, upload the relevant chapter folder or section file.

> Note: Figures/images embedded in the Word document are referenced by their captions where present; this export focuses on text and tables.



---

See `REVISION_NOTES.md` for the summarized hardware/protocol updates.
