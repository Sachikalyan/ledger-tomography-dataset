#!/usr/bin/env python3
"""
prepare.py — Ledger Tomography: Recovering Hidden Match Results From Season Tallies

Deterministically converts the raw openfootball/football.json snapshot (CC0), given as a ZIP
or an extracted directory (with or without a parent folder), OR — if given the already-prepared
Ledger Tomography dataset (the derived dataset registered on the platform) — simply separates
the public files from the private answer key and verifies their integrity.
into the competitor-facing public files and the private answer key.

Usage:
    python prepare.py --raw raw/football_json_snapshot.zip --out data --seed 20260929

Outputs:
    <out>/public/train_cases.csv, train_tallies.csv, train_fixtures.csv, train_results.csv, train_halftime.csv
    <out>/public/test_cases.csv,  test_tallies.csv,  test_fixtures.csv,  test_results.csv,  test_halftime.csv
    <out>/public/sample_submission.csv
    <out>/private/answers.csv          (grader input; never distributed)
    <out>/private/case_manifest.csv    (audit only: case -> source season/league)
    <out>/private/prepare_report.json  (audit statistics)

Design (see PROBLEM_DESCRIPTION.md / DECISION_LOG.md):
  * A case is one complete, balanced league season (every ordered home/away pair
    appears the same number of times, all full-time scores present).
  * Teams are re-labelled T01..Tnn with a seeded permutation per case; dates,
    times, league and season identity are dropped; only round index survives.
  * A reveal regime hides a subset of fixtures (scatter / tail / cluster /
    half-time variants).  Full-season tallies (P,W,D,L,GF,GA) are always shown.
  * Row order is shuffled with the seed; IDs are assigned after shuffling and
    never depend on results, teams, league, or season.
  * Two regimes (cluster30, tailhalf40) and a set of league families appear only
    in the test split ("hard composition" and "unseen league" slices).
Only the Python standard library is required.
"""
import argparse
import csv
import io
import json
import math
import os
import random
import re
import zipfile
from collections import Counter, defaultdict

# ----------------------------------------------------------------------------
# Configuration (mirrors config.json; keep in sync)
# ----------------------------------------------------------------------------
MIN_TEAMS = 10
EXCLUDE_PREFIXES = ("uefa", "copa", "mls")     # cups / non-league formats
EXCLUDE_SUFFIXES = (".cup",)

# League families that appear ONLY in the test split (unseen-league slice)
HOLDOUT_FAMILIES = {"es.2", "de.3", "ch.1", "ch.2", "ru.1", "ru.2", "tr.1", "jp.1",
                    "gr.1", "cn.1", "cz.1", "it.2", "br.1"}
# Famous top flights: only seasons >= 2024-25 may enter the test split
TOP_FLIGHTS = {"en.1", "de.1", "es.1", "it.1", "fr.1"}
TOP_FLIGHT_TEST_SEASONS = {"2024-25", "2025-26"}
# Fraction of remaining (non-top, non-holdout) family seasons routed to test
MIXED_TEST_FRACTION = 0.20

TRAIN_REGIMES = ["scatter40", "scatter60", "tail40", "cluster20", "aggregate100", "coarse60", "noisy60"]
HARD_REGIMES = ["cluster30", "coarse_aggregate100"]
TEST_REGIMES = TRAIN_REGIMES + HARD_REGIMES
# v3 (2026-10-05): half-time scores are exposed in every case wherever the source records them.
# Regimes differ in which full-time results are hidden AND in how much of the table is published:
# "full" tables give P/W/D/L/GF/GA, "coarse" tables give only played, points and goal difference.
REGIME_SPEC = {
    "scatter40":  {"kind": "scatter", "frac": 0.40, "ht": True},
    "scatter60":  {"kind": "scatter", "frac": 0.60, "ht": True},
    "aggregate100": {"kind": "scatter", "frac": 1.00, "ht": True},                   # aggregate-only: no visible results at all
    "coarse60":     {"kind": "scatter", "frac": 0.60, "ht": True, "table": "coarse"}, # privacy axis: table shows points + goal difference only
    "noisy60":      {"kind": "scatter", "frac": 0.60, "ht": True, "table": "noisy"},  # forensic axis: full table with sparsely corrupted rows
    "coarse_aggregate100": {"kind": "scatter", "frac": 1.00, "ht": True, "table": "coarse"},
    "tail40":     {"kind": "tail",    "frac": 0.40, "ht": True},
    "cluster20":  {"kind": "cluster", "frac": 0.20, "ht": True},
    "cluster30":  {"kind": "cluster", "frac": 0.30, "ht": True},
}


# ----------------------------------------------------------------------------
# Raw parsing
# ----------------------------------------------------------------------------
def _iter_raw_json(raw):
    """Yield (season, filename, bytes) for every <season>/<league>.json in a ZIP or a directory,
    regardless of any parent folder (e.g. football.json-master/) in the archive."""
    import re
    pat = re.compile(r"(?:^|/)(\d{4}(?:-\d{2})?)/([^/]+\.json)$")
    if os.path.isdir(raw):
        items = []
        for root, _, files in os.walk(raw):
            for fn in files:
                items.append(os.path.relpath(os.path.join(root, fn), raw).replace(os.sep, "/"))
        for n in sorted(items):
            m = pat.search(n)
            if m:
                with open(os.path.join(raw, n), "rb") as f:
                    yield m.group(1), m.group(2), f.read()
    else:
        with zipfile.ZipFile(raw) as z:
            for n in sorted(z.namelist()):
                m = pat.search(n)
                if m:
                    yield m.group(1), m.group(2), z.read(n)


def load_cases_from_zip(zpath):
    """Return list of dicts: {season, family, teams, fixtures:[(round_idx, home, away, hg, ag, ht)]}
    zpath may be the raw ZIP or an already-extracted directory."""
    out = []
    if True:
        seen = {}
        content_seen = set()
        for season, fn, raw_bytes in _iter_raw_json(zpath):
            n = season + "/" + fn
            if fn == "package.json":
                continue
            league = fn[:-5]
            family = league.replace("-full", "")
            if family.startswith(EXCLUDE_PREFIXES) or family.endswith(EXCLUDE_SUFFIXES):
                continue
            try:
                d = json.loads(raw_bytes.decode("utf-8"))
            except Exception:
                continue
            ms = d.get("matches") if isinstance(d, dict) else None
            if not isinstance(ms, list) or not ms:
                continue
            ms = [m for m in ms if isinstance(m, dict) and m.get("stage") in (None, "Regular")]
            pairs = Counter()
            rows = []
            ok = True
            for m in ms:
                sc = m.get("score") if isinstance(m.get("score"), dict) else {}
                ft = sc.get("ft")
                if not (isinstance(ft, list) and len(ft) == 2 and all(isinstance(x, int) and x >= 0 for x in ft)):
                    ok = False
                    break
                ht = sc.get("ht")
                if not (isinstance(ht, list) and len(ht) == 2 and all(isinstance(x, int) and x >= 0 for x in ht)):
                    ht = None
                rd = m.get("round")
                mm = re.search(r"(\d+)", str(rd)) if rd is not None else None
                if mm is None:
                    ok = False
                    break
                t1, t2 = m.get("team1"), m.get("team2")
                if not isinstance(t1, str) or not isinstance(t2, str) or t1 == t2:
                    ok = False
                    break
                pairs[(t1, t2)] += 1
                rows.append((int(mm.group(1)), t1, t2, ft[0], ft[1], ht))
            if not ok or not rows:
                continue
            teams = sorted({t for pr in pairs for t in pr})
            T = len(teams)
            if T < MIN_TEAMS:
                continue
            counts = set(pairs.values())
            if len(counts) != 1 or len(pairs) != T * (T - 1):
                continue  # not a balanced complete schedule
            key = (season, family)
            # de-duplicate: prefer '-full' variants (complete snapshots)
            if key in seen and not league.endswith("-full"):
                continue
            # de-duplicate by CONTENT: upstream occasionally files the same season under two
            # league codes (e.g. ru.2 2019-20 is a byte-identical copy of ru.1 2019-20)
            content_sig = tuple(sorted((r[1], r[2], r[3], r[4]) for r in rows))
            if content_sig in content_seen:
                continue
            content_seen.add(content_sig)
            # re-index rounds 1..R by numeric order of appearance
            round_vals = sorted({r[0] for r in rows})
            rmap = {v: i + 1 for i, v in enumerate(round_vals)}
            fixtures = [(rmap[r[0]],) + r[1:] for r in rows]
            seen[key] = {"season": season, "family": family, "league_file": league,
                         "teams": teams, "fixtures": fixtures, "pair_mult": counts.pop()}
        out = [seen[k] for k in sorted(seen)]
    return out


# ----------------------------------------------------------------------------
# Masking
# ----------------------------------------------------------------------------
def build_mask(regime, n_fix, rounds, home_idx, away_idx, T, rng):
    spec = REGIME_SPEC[regime]
    kind, frac = spec["kind"], spec["frac"]
    if kind == "scatter":
        k = int(round(frac * n_fix))
        hidden = set(rng.sample(range(n_fix), k))
    elif kind == "tail":
        R = max(rounds)
        cut = R - int(math.ceil(frac * R))  # rounds > cut are hidden
        hidden = {i for i in range(n_fix) if rounds[i] > cut}
    elif kind == "cluster":
        K = max(2, int(round(frac * T)))
        chosen = set(rng.sample(range(T), K))
        hidden = {i for i in range(n_fix) if home_idx[i] in chosen or away_idx[i] in chosen}
    else:
        raise ValueError(regime)
    return hidden, spec["ht"]


# ----------------------------------------------------------------------------
# Pass-through mode: input is the already-prepared Ledger Tomography dataset
# (the derived dataset registered on the platform).  prepare.py then only
# separates public files from the private answer key and verifies integrity.
# ----------------------------------------------------------------------------
PUBLIC_FILES = ["train_cases.csv", "train_tallies.csv", "train_tallies_coarse.csv", "train_fixtures.csv", "train_results.csv", "train_halftime.csv",
                "test_cases.csv", "test_tallies.csv", "test_tallies_coarse.csv", "test_fixtures.csv", "test_results.csv", "test_halftime.csv",
                "sample_submission.csv"]
PRIVATE_FILES = ["answers.csv"]
OPTIONAL_PRIVATE = ["case_manifest.csv", "prepare_report.json"]


def _find_prepared_root(raw):
    """Return (kind, root) where kind is 'dir' or 'zip' and root is the prefix holding the CSVs."""
    if os.path.isdir(raw):
        for root, _, files in os.walk(raw):
            if "answers.csv" in files and "test_fixtures.csv" in files:
                return "dir", root
        return None
    try:
        with zipfile.ZipFile(raw) as z:
            names = z.namelist()
    except zipfile.BadZipFile:
        return None
    for n in names:
        if n.endswith("answers.csv"):
            prefix = n[: -len("answers.csv")]
            if prefix + "test_fixtures.csv" in names:
                return "zip", prefix
    return None


def prepared_layout(raw):
    return _find_prepared_root(raw) is not None


def split_prepared(raw, out):
    kind, root = _find_prepared_root(raw)
    pub, prv = os.path.join(out, "public"), os.path.join(out, "private")
    os.makedirs(pub, exist_ok=True)
    os.makedirs(prv, exist_ok=True)

    def read(name):
        if kind == "dir":
            p = os.path.join(root, name)
            return open(p, "rb").read() if os.path.exists(p) else None
        with zipfile.ZipFile(raw) as z:
            try:
                return z.read(root + name)
            except KeyError:
                return None

    for name in PUBLIC_FILES + PRIVATE_FILES:
        b = read(name)
        if b is None:
            raise SystemExit("prepared dataset is missing %s" % name)
        with open(os.path.join(pub if name in PUBLIC_FILES else prv, name), "wb") as f:
            f.write(b)
    for name in OPTIONAL_PRIVATE:
        b = read(name)
        if b is not None:
            with open(os.path.join(prv, name), "wb") as f:
                f.write(b)

    # integrity: answer ids == hidden test fixture ids == sample submission ids; no answers in public
    def ids(path, col="id", where=None):
        with open(path, newline="") as f:
            return {r[col] for r in csv.DictReader(f) if where is None or where(r)}
    hidden = ids(os.path.join(pub, "test_fixtures.csv"), where=lambda r: r["hidden"] == "1")
    ans = ids(os.path.join(prv, "answers.csv"))
    samp = ids(os.path.join(pub, "sample_submission.csv"))
    if not (hidden == ans == samp):
        raise SystemExit("id mismatch: hidden=%d answers=%d sample=%d" % (len(hidden), len(ans), len(samp)))
    leaked = hidden & ids(os.path.join(pub, "test_results.csv"))
    if leaked:
        raise SystemExit("leak: %d hidden test fixtures have a full-time score in test_results.csv" % len(leaked))
    allfix = ids(os.path.join(pub, "test_fixtures.csv"))
    if not (ids(os.path.join(pub, "test_results.csv")) == allfix - hidden):
        raise SystemExit("test_results.csv must contain exactly the visible test fixtures")
    print("pass-through mode: %d public files, %d private files, %d hidden fixtures verified"
          % (len(PUBLIC_FILES), len(PRIVATE_FILES), len(hidden)))


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20260929)
    args = ap.parse_args()

    if prepared_layout(args.raw):
        return split_prepared(args.raw, args.out)

    rng = random.Random(args.seed)
    cases = load_cases_from_zip(args.raw)
    if not cases:
        raise SystemExit("No qualifying league seasons found in raw ZIP")

    # --- split assignment (deterministic, content-independent) --------------
    fam_seasons = defaultdict(list)
    for c in cases:
        fam_seasons[c["family"]].append(c["season"])
    test_keys = set()
    for fam, seasons in sorted(fam_seasons.items()):
        seasons = sorted(seasons)
        if fam in HOLDOUT_FAMILIES:
            test_keys.update((s, fam) for s in seasons)
        elif fam in TOP_FLIGHTS:
            test_keys.update((s, fam) for s in seasons if s in TOP_FLIGHT_TEST_SEASONS)
        else:
            k = int(round(MIXED_TEST_FRACTION * len(seasons)))
            if k > 0:
                pick = rng.sample(seasons, k)
                test_keys.update((s, fam) for s in pick)
    train_families = {c["family"] for c in cases if (c["season"], c["family"]) not in test_keys}

    # --- global shuffle and ID assignment (independent of content) ----------
    order = list(range(len(cases)))
    rng.shuffle(order)
    train_cases, test_cases = [], []
    for pos, ci in enumerate(order):
        c = cases[ci]
        c["case_id"] = "C%03d" % (pos + 1)
        (test_cases if (c["season"], c["family"]) in test_keys else train_cases).append(c)

    # --- regime assignment: balanced round-robin over shuffled lists -------
    def assign(cl, regimes):
        idx = list(range(len(cl)))
        rng.shuffle(idx)
        for j, i in enumerate(idx):
            cl[i]["regime"] = regimes[j % len(regimes)]
    assign(train_cases, TRAIN_REGIMES)
    assign(test_cases, TEST_REGIMES)

    os.makedirs(os.path.join(args.out, "public"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "private"), exist_ok=True)

    pub_cases = {"train": [], "test": []}
    pub_tallies = {"train": [], "test": []}
    pub_coarse = {"train": [], "test": []}
    pub_fix = {"train": [], "test": []}
    answers = []
    manifest = []
    audit = defaultdict(lambda: defaultdict(int))

    for split, cl in (("train", train_cases), ("test", test_cases)):
        for c in sorted(cl, key=lambda x: x["case_id"]):
            T = len(c["teams"])
            perm = list(range(T))
            rng.shuffle(perm)
            label = {t: "T%02d" % (perm[i] + 1) for i, t in enumerate(c["teams"])}
            fixtures = c["fixtures"]
            n = len(fixtures)
            rounds = [f[0] for f in fixtures]
            tix = {t: i for i, t in enumerate(c["teams"])}
            hidx = [tix[f[1]] for f in fixtures]
            aidx = [tix[f[2]] for f in fixtures]
            hidden, show_ht = build_mask(c["regime"], n, rounds, hidx, aidx, T, rng)
            # tallies (full season)
            tal = {t: [0, 0, 0, 0, 0, 0] for t in c["teams"]}  # P,W,D,L,GF,GA
            for (_, h, a, hg, ag, _) in fixtures:
                tal[h][0] += 1; tal[a][0] += 1
                tal[h][4] += hg; tal[h][5] += ag; tal[a][4] += ag; tal[a][5] += hg
                if hg > ag: tal[h][1] += 1; tal[a][3] += 1
                elif hg == ag: tal[h][2] += 1; tal[a][2] += 1
                else: tal[h][3] += 1; tal[a][1] += 1
            table_kind = REGIME_SPEC[c["regime"]].get("table", "full")
            corrupted = {}
            if table_kind == "noisy":
                # sparse corruption of the PUBLISHED table only (truth is untouched): ~15 % of rows get one
                # bounded edit that keeps the row internally plausible (played unchanged, counts >= 0)
                n_bad = max(1, int(round(0.15 * len(c["teams"]))))
                for t in rng.sample(c["teams"], n_bad):
                    row = list(tal[t]); kind = rng.choice(["gf", "ga", "wd", "dl"])
                    d = rng.choice([-3, -2, -1, 1, 2, 3])
                    if kind == "gf": row[4] = max(0, row[4] + d)
                    elif kind == "ga": row[5] = max(0, row[5] + d)
                    elif kind == "wd":
                        k = min(abs(d), row[1] if d < 0 else row[2]); row[1] += -k if d < 0 else k; row[2] += k if d < 0 else -k
                    else:
                        k = min(abs(d), row[2] if d < 0 else row[3]); row[2] += -k if d < 0 else k; row[3] += k if d < 0 else -k
                    corrupted[t] = row
            for t in c["teams"]:
                if table_kind == "coarse":
                    pub_coarse[split].append([c["case_id"], label[t], tal[t][0], 3 * tal[t][1] + tal[t][2], tal[t][4] - tal[t][5]])
                else:
                    pub_tallies[split].append([c["case_id"], label[t]] + (corrupted[t] if t in corrupted else tal[t]))
            # fixture rows, shuffled before ID assignment
            fo = list(range(n))
            rng.shuffle(fo)
            ht_available = sum(1 for f in fixtures if f[5] is not None)
            for k, i in enumerate(fo):
                r, h, a, hg, ag, ht = fixtures[i]
                fid = "%s_F%03d" % (c["case_id"], k + 1)
                is_hidden = 1 if i in hidden else 0
                ht_h = ht[0] if ht is not None else ""
                ht_a = ht[1] if ht is not None else ""
                if split == "train":
                    row = [c["case_id"], fid, r, label[h], label[a], is_hidden, ht_h, ht_a, hg, ag]
                else:
                    show = show_ht
                    row = [c["case_id"], fid, r, label[h], label[a], is_hidden,
                           ht_h if show else "", ht_a if show else "",
                           "" if is_hidden else hg, "" if is_hidden else ag]
                    if is_hidden:
                        answers.append([fid, "%d-%d" % (hg, ag), c["case_id"], label[h], label[a],
                                        "regime=%s;table=%s;hard=%s;unseen_league=%s" % (
                                            c["regime"], REGIME_SPEC[c["regime"]].get("table", "full"),
                                            "yes" if c["regime"] in HARD_REGIMES else "no",
                                            "yes" if c["family"] not in train_families else "no")])
                pub_fix[split].append(row)
                key = "hidden" if is_hidden else "visible"
                audit[split + "_homewin_" + key][("H" if hg > ag else "D" if hg == ag else "A")] += 1
            # counts (teams, rounds, fixtures, hidden) are derivable from the other tables and are
            # deliberately not repeated here; flags are categorical strings, not 0/1 integers
            case_row = [c["case_id"], REGIME_SPEC[c["regime"]].get("table", "full")]
            if split == "train":
                case_row.append(c["regime"])
            pub_cases[split].append(case_row)
            manifest.append([c["case_id"], split, c["season"], c["league_file"], c["family"], c["regime"],
                             T, n, len(hidden), ht_available])
            audit["regime_counts_" + split][c["regime"]] += 1
            audit["family_counts_" + split][c["family"]] += 1

    # --- write public ------------------------------------------------------
    def w(path, header, rows):
        with open(path, "w", newline="") as f:
            cw = csv.writer(f)
            cw.writerow(header)
            cw.writerows(rows)
    P = os.path.join(args.out, "public")
    Q = os.path.join(args.out, "private")
    fix_header = ["case_id", "id", "round", "home", "away", "hidden"]
    res_header = ["case_id", "id", "ft_home", "ft_away"]
    ht_header = ["case_id", "id", "ht_home", "ht_away"]
    # wide rows -> three blank-free tables (every value in every file is populated)
    def split_tables(rows):
        fx, rs, ht = [], [], []
        for cid, fid, r, h, a, hid, hth, hta, fth, fta in rows:
            fx.append([cid, fid, r, h, a, hid])
            if fth != "":
                rs.append([cid, fid, fth, fta])
            if hth != "":
                ht.append([cid, fid, hth, hta])
        return fx, rs, ht
    tables = {sp: split_tables(pub_fix[sp]) for sp in ("train", "test")}
    tal_header = ["case_id", "team", "played", "wins", "draws", "losses", "goals_for", "goals_against"]
    w(os.path.join(P, "train_cases.csv"),
      ["case_id", "table", "regime"], pub_cases["train"])
    w(os.path.join(P, "test_cases.csv"),
      ["case_id", "table"], pub_cases["test"])
    w(os.path.join(P, "train_tallies.csv"), tal_header, pub_tallies["train"])
    w(os.path.join(P, "test_tallies.csv"), tal_header, pub_tallies["test"])
    coarse_header = ["case_id", "team", "played", "points", "goal_difference"]
    w(os.path.join(P, "train_tallies_coarse.csv"), coarse_header, pub_coarse["train"])
    w(os.path.join(P, "test_tallies_coarse.csv"), coarse_header, pub_coarse["test"])
    for sp in ("train", "test"):
        fx, rs, ht = tables[sp]
        w(os.path.join(P, "%s_fixtures.csv" % sp), fix_header, fx)
        w(os.path.join(P, "%s_results.csv" % sp), res_header, rs)
        w(os.path.join(P, "%s_halftime.csv" % sp), ht_header, ht)
    sample = [[a[0], "1-0", 0] for a in answers]
    w(os.path.join(P, "sample_submission.csv"), ["id", "target", "certain"], sample)
    # --- write private -----------------------------------------------------
    w(os.path.join(Q, "answers.csv"),
      ["id", "target", "case_id", "home", "away", "meta"], answers)
    w(os.path.join(Q, "case_manifest.csv"),
      ["case_id", "split", "season", "league_file", "family", "regime", "n_teams", "n_fixtures", "n_hidden", "ht_available"],
      manifest)
    report = {
        "seed": args.seed,
        "n_cases_total": len(cases),
        "n_train_cases": len(train_cases),
        "n_test_cases": len(test_cases),
        "n_train_fixtures": len(pub_fix["train"]),
        "n_test_fixtures": len(pub_fix["test"]),
        "n_submission_rows": len(answers),
        "train_families": sorted(train_families),
        "unseen_test_families": sorted({c["family"] for c in test_cases} - train_families),
        "audit": {k: dict(v) for k, v in audit.items()},
    }
    with open(os.path.join(Q, "prepare_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != "audit"}, indent=2))
    for k, v in sorted(report["audit"].items()):
        print(k, dict(v))


if __name__ == "__main__":
    main()
