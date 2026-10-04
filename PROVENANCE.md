# Provenance

| item | value |
|---|---|
| Upstream source | https://github.com/openfootball/football.json |
| Upstream commit | `e6744429ee395bc86f247348c6184bb08d4eb361` |
| Upstream licence | CC0 1.0 Universal (`LICENSE`) |
| Snapshot date | 2026-09-29 |
| Raw copy | `raw/football_json_raw.zip` (291 season JSON files, unmodified content, parent folder removed) |
| Derivation | `prepare.py`, seed 20260929, Python standard library, deterministic |
| Derived licence | CC0 1.0 Universal |

## Transformations
1. Season selection: regular-stage, every fixture with a full-time score, at least 10 teams, uniform ordered-pair multiplicity (291 files → 190 seasons); content-hash de-duplication removed the upstream byte-identical `2019-20/ru.2.json` (→ 189).
2. Anonymisation per case: seeded team-label permutation `T01…Tnn`; league, country, season, dates and club names removed; rounds re-indexed `1…R`; fixture ids assigned after a seeded shuffle.
3. Tallies: played / wins / draws / losses / goals for / goals against per team over all fixtures.
4. Reveal regimes (v3, 2026-10-05; half-time exposed in every case): `scatter40`, `scatter60`, `tail40`, `cluster20`, `aggregate100` (no visible result), `coarse60` (coarse table: points and goal difference only) in train and test, and `cluster30`, `coarse_aggregate100` test-only; hidden fixtures' full-time scores removed from `test_results.csv` and recorded as `target` (`H-A`) in `answers.csv`, keyed by `id`.
5. Split: 132 train / 57 test cases; twelve league families test-only; top-flight seasons 2024-25 and 2025-26 test-only.

No personal data are contained in the derived files.
