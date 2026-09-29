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
An inverse-inference dataset built from complete football league seasons. Each of 189 **cases** is one full season (10–24 teams, 132–552 fixtures) in which every fixture's home/away pairing and round are known, a regime-specific subset of full-time results has been **hidden**, and the **exact end-of-season tallies** of every team (played, wins, draws, losses, goals for, goals against — computed over all fixtures, hidden ones included) are published. The task supported by the dataset is to reconstruct the hidden scorelines jointly, using the tallies as exact constraints, and to say which reconstructions are certain.

All identities are removed: leagues, countries, seasons, dates and club names are gone; teams are relabelled `T01…Tnn` by an independent seeded permutation per case; rounds are re-indexed `1…R`; fixture ids are assigned after a seeded shuffle. Seven reveal regimes were applied (five appear in the training split with labels; two harder compositions appear only in the test split, unlabelled). Twelve league families appear only in the test split.

Derived deterministically (seed 20260929, ~1 s, Python standard library) from the CC0 openfootball `football.json` snapshot at commit `e6744429ee395bc86f247348c6184bb08d4eb361`, keeping only complete, balanced regular-stage seasons (190 found, 1 byte-identical upstream duplicate removed). Source data are facts (match results) dedicated to the public domain; no source names, dates or identifiers survive in this dataset.

## File Structure
All 12 files are flat CSVs with a header row and **no missing values in any column**; the files are joined on `fixture_id` (and `case_id`).
- `train_cases.csv` — 132 rows, one per training case, with its reveal `regime` label
- `train_tallies.csv` — 2,478 rows, full-season tallies of every team in every training case
- `train_fixtures.csv` — 47,338 rows, the complete schedule of every training case with a `hidden` flag marking which fixtures the regime would hide
- `train_results.csv` — 47,338 rows, the full-time score of **every** training fixture
- `train_halftime.csv` — 43,891 rows, the half-time score of every training fixture for which the source recorded one
- `test_cases.csv` — 57 rows, one per test case (no regime label)
- `test_tallies.csv` — 1,039 rows, full-season tallies of every team in every test case
- `test_fixtures.csv` — 19,646 rows, the complete schedule of every test case; `hidden = 1` on the 9,438 withheld fixtures
- `test_results.csv` — 10,208 rows, the full-time score of the **visible** test fixtures only
- `test_halftime.csv` — 5,035 rows, half-time scores for fixtures (hidden ones included) of the test cases whose regime exposes half-time
- `sample_submission.csv` — 9,438 rows, one per hidden test fixture, in the required output format
- `answers.csv` — 9,438 rows, the private answer key for the hidden test fixtures (must not be exposed to solvers)

## Features

### `train_cases.csv` / `test_cases.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id` | string | `C001`…`C189`; unique season identifier, order-free |
| `n_teams` | int | 10, 12, 16, 18, 20 or 24 |
| `n_rounds` | int | 22–46 |
| `n_fixtures` | int | 132–552; equals rounds × teams / 2 |
| `n_hidden` | int | number of fixtures with `hidden = 1` |
| `ht_provided` | int {0,1} | 1 if half-time scores are exposed for this case in the test condition |
| `regime` | string (train only) | one of `scatter40`, `scatter60`, `tail40`, `cluster20`, `halftime60` — the mechanism used to choose hidden fixtures |

### `train_tallies.csv` / `test_tallies.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id` | string | case reference |
| `team` | string | `T01`…`Tnn`, per-case anonymised label |
| `played` | int | fixtures played (= 2·(n_teams−1) or 4·(n_teams−1)) |
| `wins`, `draws`, `losses` | int | full-season counts over all fixtures, hidden included |
| `goals_for`, `goals_against` | int | full-season goal totals over all fixtures, hidden included |

### `train_fixtures.csv` / `test_fixtures.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id` | string | case reference |
| `fixture_id` | string | `Cnnn_Fnnn`, unique, assigned after a seeded shuffle (carries no information) |
| `round` | int | 1…R, chronological |
| `home`, `away` | string | team labels |
| `hidden` | int {0,1} | 1 = full-time result withheld in the test condition |

### `train_results.csv` / `test_results.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id`, `fixture_id` | string | references |
| `ft_home`, `ft_away` | int | full-time goals, home then away (0–13 observed); train: all fixtures; test: visible fixtures only |

### `train_halftime.csv` / `test_halftime.csv`
| Column | Type | Description |
|--------|------|-------------|
| `case_id`, `fixture_id` | string | references |
| `ht_home`, `ht_away` | int | half-time goals, home then away; present only where the source recorded them and (test) where the case's regime exposes half-time |

### `sample_submission.csv`
| Column | Type | Description |
|--------|------|-------------|
| `fixture_id` | string | one row per hidden test fixture |
| `home_goals`, `away_goals` | int 0–30 | predicted full-time score (sample: 1–0) |
| `certain` | int {0,1} | 1 = commit to the predicted outcome (sample: 0) |

### `answers.csv` (private)
| Column | Type | Description |
|--------|------|-------------|
| `fixture_id`, `case_id` | string | references |
| `regime` | string | one of the seven regimes incl. test-only `cluster30`, `tailhalf40` |
| `hard` | int {0,1} | 1 for the two test-only composition regimes |
| `unseen_league` | int {0,1} | 1 if the case's league family has no training case |
| `home`, `away` | string | team labels |
| `ft_home`, `ft_away` | int | true full-time goals |

## Characteristics
- Every case is a complete balanced schedule: each ordered (home, away) pair occurs the same number of times (once in most cases; twice in a few 10-team seasons).
- Hidden-fixture outcome shares (home 0.43, draw 0.27, away 0.30) match visible shares in every regime; the most common scorelines are 1-1, 1-0, 2-1, 0-0, 0-1, 2-0 in both splits.
- Only 14 of the 9,438 hidden fixtures are logically forced by the tallies alone; the rest are constrained but not determined.
- Test regime counts: scatter40 9, scatter60 8, tail40 8, cluster20 8, halftime60 8, cluster30 8, tailhalf40 8 cases.
- Audits: 0 duplicate tally signatures and 0 duplicate visible-result signatures across cases; fixture-id blocks and team-label magnitude are uninformative about outcomes.
- No personal data.