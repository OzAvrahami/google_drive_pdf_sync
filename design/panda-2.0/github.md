repo: OzAvrahami/google_drive_pdf_sync
branch: main
path: docs/

## Last sync
date: 2026-08-17T20:20:00Z

### Updated in this project
- Read all 8 current-state docs as source of truth for the Panda 2.0 UX redesign.
- Established the Panda 2.0 information architecture, daily workflow model, and old→new terminology mapping.
- Explored two visual directions; user chose a hybrid (1B dark rail + 1A warm work surface).
- Built the full hybrid set in `Panda 2.0.dc.html`: shell + 6 views + refined Document Workspace + states.

## Screen map
Two project files. `Panda 2.0 Explorations.dc.html` = UX brief + directions 1A/1B (history). `Panda 2.0.dc.html` = chosen hybrid full set.

| Project screen (Panda 2.0.dc.html) | Repo source |
| --- | --- |
| Application shell + dark work rail + task dock | docs/UI_INVENTORY.md (SidebarWidget, MainWindow, toolbar), docs/ARCHITECTURE.md |
| Overview dashboard | docs/UI_INVENTORY.md (Dashboard), docs/PRODUCT_FLOWS.md (#2,#3,#11) |
| Inbox / New | docs/PRODUCT_FLOWS.md (#2,#3), docs/DATA_MODEL.md (status new) |
| Needs Attention | docs/PRODUCT_FLOWS.md (#8,#12,#14,#15), docs/UI_INVENTORY.md (attention filters) |
| Ready (processed+approved) | docs/PRODUCT_FLOWS.md (#8,#10,#11), docs/DATA_MODEL.md (processed/approved) |
| Irrelevant | docs/PRODUCT_FLOWS.md (#13), docs/DATA_MODEL.md (confirmed_irrelevant/excluded) |
| History | docs/PRODUCT_FLOWS.md (#11), docs/UI_INVENTORY.md (History) |
| Document Workspace + duplicate resolve | docs/PRODUCT_FLOWS.md (#9 Review,#15 dup), docs/UI_INVENTORY.md (Review Dialog) |
| Background task center | docs/PRODUCT_FLOWS.md (#2,#3,#17), docs/UI_INVENTORY.md (Progress Dialog) |
| Status / badge system | docs/DATA_MODEL.md (workflow statuses), docs/PRODUCT_FLOWS.md (#8 confidence) |
