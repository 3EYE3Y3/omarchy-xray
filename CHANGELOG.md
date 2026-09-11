# Changelog

## 0.9.1 - 2026-09-11

- Added integer `rss_bytes` and `virtual_memory_bytes` fields to structured process overviews while preserving the existing human-readable fields and schema version 1.
- Excluded X-Ray's own process branch and reliably identified pipe/job peers from process trees without filtering by executable name.

## 0.9.0 - 2026-09-11

- Initial local-acceptance candidate.
- Structured probes for windows, processes, ports, files, disks, services, Arch packages, domains, IPs, interfaces, and system health.
- Native Omarchy overlay, live refresh, process HUD mode, and X-Ray Vision toggle.
- Local-first CLI and doctor diagnostics.
