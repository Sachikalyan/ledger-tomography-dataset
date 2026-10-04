# Ledger Tomography dataset

Partial football ledgers with exact season tallies — 189 anonymised complete seasons, an inverse-reconstruction target and a private answer key. Released under CC0 1.0.

This repository is the canonical public home of the dataset; the challenge platform entry points here. File checksums are in `SHA256SUMS`.

## Provenance and regeneration
Derived from the CC0 openfootball `football.json` snapshot at commit `e6744429ee395bc86f247348c6184bb08d4eb361` (https://github.com/openfootball/football.json, downloaded 2026-09-29), a copy of which is kept unmodified in `raw/football_json_raw.zip`. Regenerate byte-identically with:

```
python prepare.py --raw raw/football_json_raw.zip --out data --seed 20260929
```

`prepare.py` needs only the Python standard library and runs in about one second. `answers.csv` is the private answer key and must not be exposed to challenge solvers; `prepare.py` given this repository (or its ZIP) separates it from the public files and checks their integrity.


## Overview
An inverse-inference dataset built from complete football league seasons. Each of 189 **cases** is one full season (10–24 teams, 132–552 fixtures) in which every fixture's home/away pairing and round are known, a regime-specific subset of full-time results has been **hidden**, and the **exact end-of-season tallies** of every team (played, wins, draws, losses, goals for, goals against — computed over all fixtures, hidden ones included) are published, together with the half-time score of every fixture for which the source recorded one (about 92 %, hidden fixtures included). The task supported by the dataset is to reconstruct the hidden full-time scorelines jointly — learning how second halves unfold from the training seasons and using the tallies as exact constraints — and to say which reconstructions are certain. (Version 3, 2026-10-05: half-time scores are exposed in every case; cases vary in which fixtures are hidden — including aggregate-only cases with no visible result — and in whether the published table is full (P/W/D/L/GF/GA) or coarse (played, points, goal difference only).)

All identities are removed: leagues, countries, seasons, dates and club names are gone; teams are relabelled `T01…Tnn` by an independent seeded permutation per case; rounds are re-indexed `1…R`; fixture ids are assigned after a seeded shuffle. Seven reveal regimes were applied (five appear in the training split with labels; two harder compositions appear only in the test split, unlabelled). Twelve league families appear only in the test split.

Derived deterministically (seed 20260929, ~1 s, Python standard library) from the CC0 openfootball `football.json` snapshot at commit `e6744429ee395bc86f247348c6184bb08d4eb361`, keeping only complete, balanced regular-stage seasons (190 found, 1 byte-identical upstream duplicate removed). Source data are facts (match results) dedicated to the public domain; no source names, dates or identifiers survive in this dataset.

## File Structure
All 12 files are flat CSVs with a header row, **no missing values in any column** and no heavy-tailed numeric columns (flags are categorical `yes`/`no`; per-case counts are derivable rather than stored); the files are joined on `id` (and `case_id`).
- `train_cases.csv` — 132 rows, one per training case: `table` kind and reveal `regime` label
- `train_tallies_coarse.csv` — 412 rows, the coarse table (played, points, goal difference) of every team of every coarse-table training case
- `train_tallies.csv` — 2,066 rows, full-season tallies of every team in every full-table training case
- `train_fixtures.csv` — 47,338 rows, the complete schedule of every training case with a `hidden` flag marking which fixtures the regime would hide
- `train_results.csv` — 47,338 rows, the full-time score of **every** training fixture
- `train_halftime.csv` — 43,891 rows, the half-time score of every training fixture for which the source recorded one
- `test_cases.csv` — 57 rows, one per test case: `table` kind only
- `test_tallies_coarse.csv` — 247 rows, coarse tables of the coarse-table test cases
- `test_tallies.csv` — 792 rows, full-season tallies of every team in every full-table test case
- `test_fixtures.csv` — 19,646 rows, the complete schedule of every test case; `hidden = 1` on the 11,916 withheld fixtures
- `test_results.csv` — 7,730 rows, the full-time score of the **visible** test fixtures only
- `test_halftime.csv` — 18,043 rows, half-time scores of every test fixture (hidden ones included) for which the source recorded one
- `sample_submission.csv` — 11,916 rows, one per hidden test fixture, in the required output format
- `answers.csv` — 11,916 rows, the private answer key for the hidden test fixtures (must not be exposed to solvers)

## Features

### `train_cases.csv` / `test_cases.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id` | string | `C001`…`C189`; unique season identifier, order-free |
| `table` | string {`full`, `coarse`} | which table is published for the case (full tallies file or coarse tallies file) |
| `regime` | string (train only) | one of `scatter40`, `scatter60`, `tail40`, `cluster20`, `aggregate100`, `coarse60` — the mechanism used to choose hidden fixtures (and, for coarse60, the coarse table) |

Team count (10, 12, 16, 18, 20 or 24), round count (22–46), fixture count (132–552) and hidden count per case are derivable from the tallies and fixtures tables and are not repeated here.

### `train_tallies_coarse.csv` / `test_tallies_coarse.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id`, `team` | string | references |
| `played` | int | fixtures played |
| `points`, `goal_difference` | int | full-season points (3/1/0) and goals for minus goals against, over all fixtures |

### `train_tallies.csv` / `test_tallies.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id` | string | case reference |
| `team` | string | `T01`…`Tnn`, per-case anonymised label |
| `played` | int | fixtures played (= 2·(teams−1) or 4·(teams−1)) |
| `wins`, `draws`, `losses` | int | full-season counts over all fixtures, hidden included |
| `goals_for`, `goals_against` | int | full-season goal totals over all fixtures, hidden included |

### `train_fixtures.csv` / `test_fixtures.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id` | string | case reference |
| `id` | string | fixture identifier `Cnnn_Fnnn`, unique across the dataset, assigned after a seeded shuffle (carries no information) |
| `round` | int | 1…R, chronological |
| `home`, `away` | string | team labels |
| `hidden` | int {0,1} | 1 = full-time result withheld in the test condition |

### `train_results.csv` / `test_results.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id`, `id` | string | references |
| `ft_home`, `ft_away` | int | full-time goals, home then away (0–13 observed); train: all fixtures; test: visible fixtures only |

### `train_halftime.csv` / `test_halftime.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id`, `id` | string | references |
| `ht_home`, `ht_away` | int | half-time goals, home then away; present wherever the source recorded them (both splits, hidden fixtures included) |

### `sample_submission.csv`
| Column | Type | Description |
|--------|------|-------------|
| `id` | string | one row per hidden test fixture |
| `target` | string | predicted full-time score as `H-A`, e.g. `2-1` (sample: `1-0`) |
| `certain` | int {0,1} | 1 = commit to the predicted outcome (sample: 0) |

### `answers.csv` (private)
| Column | Type | Description |
|--------|------|-------------|
| `id` | string | hidden test fixture identifier |
| `target` | string | true full-time score as `H-A`, e.g. `2-1` |
| `case_id` | string | case reference |
| `meta` | string | `regime=…;table=…;hard=…;unseen_league=…` — reveal regime (one of eight incl. test-only `cluster30`, `coarse_aggregate100`), table kind, test-only flag, unseen-league flag |
| `home`, `away` | string | team labels |

## Characteristics
- Every case is a complete balanced schedule: each ordered (home, away) pair occurs the same number of times (once in most cases; twice in a few 10-team seasons).
- Hidden-fixture outcome shares (home 0.43, draw 0.27, away 0.30) match visible shares in every regime; the most common scorelines are 1-1, 1-0, 2-1, 0-0, 0-1, 2-0 in both splits.
- Only a handful of the 11,916 hidden fixtures are logically forced by the tallies alone; the rest are constrained but not determined.
- Test regime counts: scatter40 8, scatter60 7, tail40 7, cluster20 7, aggregate100 7, coarse60 7, cluster30 7, coarse_aggregate100 7 cases.
- Audits: 0 duplicate tally signatures and 0 duplicate visible-result signatures across cases; fixture-id blocks and team-label magnitude are uninformative about outcomes.
- No personal data.