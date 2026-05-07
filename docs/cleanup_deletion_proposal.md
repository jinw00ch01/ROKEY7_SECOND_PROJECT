# Cleanup Deletion Proposal

> **No deletions in this document.** This is a proposal — every command
> below is presented as text, never executed by it. Read this in
> conjunction with `_archive_cleanup/20260508/cleanup_manifest.md`.

This proposal is conservative on purpose: ambiguous files stay archived
rather than being deleted, and items the prior cleanup rules excluded
(ROS package dirs, config files, calibration files) are kept in place
even when their references showed zero hits. The rationale is that
restoring is cheap, while losing a file someone quietly depends on is
expensive.

---

## 1. Files/folders safely archived (already moved)

These six files were moved with `git mv` to
`_archive_cleanup/20260508/` on 2026-05-08. They are no longer in the
active tree but remain version-controlled in the archive. The post-move
mock dry-run reached `[state] done` with 8/8 successful picks, so none
of them was load-bearing.

| Original path | Archived path |
|---|---|
| `cobot_voice/scripts/publish_robot_session_scenarios.py` | `_archive_cleanup/20260508/cobot_voice/scripts/publish_robot_session_scenarios.py` |
| `web_stt_firebase/STEPS2WEBinLOCAL.md` | `_archive_cleanup/20260508/web_stt_firebase/STEPS2WEBinLOCAL.md` |
| `experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv` | `_archive_cleanup/20260508/experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv` |
| `experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv` | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv` |
| `experiments/cobot_OD_obb_small/train_log.txt` | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/train_log.txt` |
| `experiments/cobot_OD_obb_small/tune_log.txt` | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/tune_log.txt` |

---

## 2. Files/folders that can likely be permanently deleted later

These are split into three confidence tiers. Higher tier = safer to delete.

### Tier A — already archived, deletion later is safe

After the waiting period (§6), these can be removed with high
confidence. They produced **zero** reference hits across `cobot_*/`,
`conveyor_controller/`, `scripts/`, `web_stt_firebase/`, and
`docs/01..04` (see prior verification report §1) and the dry-run did
not need them.

- `_archive_cleanup/20260508/web_stt_firebase/STEPS2WEBinLOCAL.md`
- `_archive_cleanup/20260508/experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv`
- `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv`
- `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/train_log.txt`
- `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/tune_log.txt`

### Tier B — not yet archived; safe to remove after owner sign-off

These were excluded from the archive move by rules 1–4 but the
verification report classified them as confirmed-unused. Each one
needs a one-line owner approval, then can be deleted.

- `cobot_voice/cobot_voice/voice_processing_node.py` — legacy ROS node;
  no in-tree subscriber to its `/voice/text` / `/voice/status` topics.
  Production voice path (`scripts/voice_to_robot.py` → `voice_order_flow`
  → `task_manager_dispatcher`) bypasses ROS topics entirely. Removing
  the file also requires removing line 26 of `cobot_voice/setup.py`
  (the `voice_processing = …` `console_scripts` entry).
- `cobot_voice/keyword_extraction.py` (top-level shim, 18 lines) —
  superseded by `scripts/voice_to_robot.py --text "..."`.
- `cobot_voice/voice_order_flow.py` (top-level 5-line shim) — only
  referenced by *already-superseded* docs; functionally identical to
  `python3 -m cobot_voice.voice_order_flow`.
- `cobot_config/config/handeye.yaml` — reference values only; runtime
  binding is `gripper2camera_npy` in `cobot_perception/config/perception.yaml`.
- `cobot_config/config/workspace.yaml` — reference values only; runtime
  bounds live in `task_manager.yaml` and `robot_control.yaml`.
- `cobot_config/config/slot_poses.yaml` — input for the unimplemented
  `cobot_policy` package.
- `cobot_config/config/policy_config.yaml` — same.
- `cobot_config/config/object_aliases.yaml` — runtime alias map is the
  Python dict in `cobot_voice/cobot_voice/object_aliases.py`.

### Tier C — needs a roadmap decision before removal

These are kept-but-empty placeholders. Either implement them or remove;
"keep as a stub" is the worst of both worlds because new readers
mistake them for real packages.

- `cobot_safety/` (whole package — 0-byte module files) — currently
  declared in `cobot_safety/setup.py` with a `safety_manager` entry
  point that would crash on launch. Mentioned in
  `cobot_bringup/launch/host_system.launch.py:3` as a future-phase
  placeholder.
- `cobot_policy/` (whole package — 0-byte module files) — same.
- `nuts_data_recording/` (whole package) — calibration-data recording
  tool. Builds, but not referenced by any active launch or doc. Keep
  if the team plans to recalibrate; remove if obsolete.
- `cobot_bringup/config/params.yaml` — preferred resolution is to
  **wire it into `cobot_bringup/launch/full_system.launch.py`** so
  `ROS_DOMAIN_ID` and `RMW_IMPLEMENTATION` are actually enforced. If
  the team prefers shell-set values, then delete.
- `experiments/cobot_OD_obb_small/` (entire alternative-model run,
  except `weights/best.pt` which is allow-listed in `.gitignore`) — the
  production model is the *nano* variant. The "small" variant is a
  retained alternative; confirm whether it is intentionally kept.
- `experiments/cobot_OD_obb_*/train_phase1_2026*/` — phase-1 training
  outputs, superseded by phase-2. Each holds only `args.yaml` +
  `results.csv` (plus gitignored caches/weights). Pure history.

### Tier D — out of scope; handle with `git rm --cached`, not `rm`

These are tracked-but-`.gitignore`-matched Firebase tooling caches
identified in the prior `.gitignore` step. They should be **untracked**
(removed from the index) but **kept on disk** because firebase-tools
regenerates them.

- `web_stt_firebase/.firebase/.graphqlrc`
- `web_stt_firebase/.firebase/INSTRUCTIONS.md`
- `web_stt_firebase/dataconnect/.dataconnect/schema/prelude.gql`

### Tier E — rebuild artifacts (non-git deletion)

The stale `command_parser` and `firebase_state_bridge` launcher
scripts in `install/cobot_voice/lib/cobot_voice/` are install-tree
leftovers from a build that predates the integration cleanup. They
are not in `cobot_voice/setup.py`. To clean them up:

```bash
# Run NOTHING from this proposal automatically.
rm -rf build/ install/ log/
colcon build --symlink-install
```

This is local-disk hygiene, not a git operation.

---

## 3. Files/folders that should remain archived for now

Even after the waiting period, the following archived files are worth
keeping in `_archive_cleanup/20260508/` rather than deleting outright,
because they have downstream value beyond runtime use.

- `_archive_cleanup/20260508/cobot_voice/scripts/publish_robot_session_scenarios.py`
  — only known tool to manually push `robot_session/current` snapshots
  into Firestore. Useful for demoing the web UI without a robot. Keep
  archived; promote back into `cobot_voice/scripts/` if demos resume.

The remaining archived files (conf_sweep CSVs, train/tune logs, the
local-setup memo) can graduate from "archived" to "deleted" per
Tier A above once the waiting period passes — but **only as a batch**,
not piecemeal, so the archive's history is easy to audit.

---

## 4. Files/folders restored or excluded

**Restored from archive: none.** The mock dry-run reached `[state] done`
with all 8 picks succeeding, confirming no archived file was needed.

**Excluded from this proposal (i.e., never moved, never proposed for
deletion):**

- All entries in §3 of the prior verification report
  (`cobot_voice/voice_processing_node.py`, the in-package shims,
  `nuts_data_recording/`, `cobot_safety/`, `cobot_policy/`, the seven
  `cobot_config/*.yaml` files, `cobot_bringup/config/params.yaml`,
  `experiments/cobot_OD_obb_small/`, the `train_phase1_*` dirs, the
  legacy `docs/*.md` files, the Firebase-tooling caches).
- All "must keep" entries in §2 of the prior verification report
  (active source code, ROS package directories that are wired into
  launch files, `cobot_msgs/{msg,srv,action}/*`, the production model
  weights, the four canonical `docs/0[1-4]_*.md` files,
  `cobot_voice/resource/{.env.example, hello_rokey_8332_32.tflite}`,
  `secrets_4_firebase_config/`, the `web_stt_firebase/{src,public,…}`
  source tree, the `pick_offsets.yaml` shared source of truth, etc.).

The legacy `docs/{run_manual.md, voice_to_robot_integration_plan.md,
three_firebase_bridge_*.md, nut_recommendation_*.md,
stt_db_tts_robot_integration.md}` are noted as superseded inside
`docs/01_system_architecture.md`. Recommended path is **migration to
`docs/_archive/`**, not deletion — same conservative rationale: the
docs trace the project's design history.

---

## 5. Risks

| Risk | Affected items | Mitigation |
|---|---|---|
| ML reproducibility loss | Tier A `conf_sweep_*.csv`, `train_log.txt`, `tune_log.txt` | These document how the production `best.pt` was produced. Once deleted, the chain "data → hyperparameters → model" is no longer auditable. **Mitigation**: archive a copy outside the repo (S3, internal Drive) before any `rm`. |
| Demo capability loss | `publish_robot_session_scenarios.py` | This is the only known manual-injection tool for the web demo. **Mitigation**: keep archived indefinitely (see §3). |
| Calibration regression | Tier B `cobot_config/handeye.yaml` | Even though no runtime loader reads it, it documents the team's reference depth offset. **Mitigation**: copy its contents into `docs/01_system_architecture.md` as a calibration-history note before deleting. |
| Empty-package re-creation cost | Tier C `cobot_safety/`, `cobot_policy/` | If the team ever decides to implement them, recreating the `package.xml` + `setup.py` skeleton is ~15 minutes per package, but the namespaces (already used in launch comments) need to come back. **Mitigation**: capture intended scope in a roadmap doc before removing. |
| Calibration tool re-creation | Tier C `nuts_data_recording/` | Custom tool tied to DSR_ROBOT2 conventions. Re-implementing from scratch is non-trivial. **Mitigation**: confirm with the calibration owner that no future recalibration will use it. |
| Discovery confusion | Tier D Firebase caches | If `git rm --cached` is run but `.gitignore` is not yet applied, the next `git add` will re-track them. **Mitigation**: confirm the new `.gitignore` rules from the previous step are committed before running the `git rm --cached`. |
| Hidden dependencies via legacy docs | The seven legacy docs in `docs/` | They contain stale instructions; if a teammate reads them and follows the steps, the obsolete `~/cobot_ws/` paths and `--z-override 315` calibration values will mislead them. **Mitigation**: prefer migration to `docs/_archive/` over outright deletion, with a banner at the top of each archived file pointing at the new docs. |
| Loss of model alternative | Tier C `experiments/cobot_OD_obb_small/` | Removing the small model variant erases the team's fallback if the nano model regresses. **Mitigation**: keep `weights/best.pt` (already gitignored allow-list) on disk; archive `args.yaml`/`results.csv`/etc. only after a release of the nano model that has been stable for 30+ days in production. |
| Stale install-tree artifacts | Tier E `install/cobot_voice/lib/cobot_voice/{command_parser, firebase_state_bridge}` | These are local-disk only; not git. **Mitigation**: zero — `rm -rf build/ install/ log/` is non-destructive and recoverable by re-building. |

---

## 6. Recommended waiting period before deletion

> **Earliest deletion date for any Tier A item: 2026-06-07 (30 days
> after archival).**

The schedule below pairs each tier with a gate, not just a calendar
date. Both must be satisfied.

| Tier | Calendar gate | Verification gate |
|---|---|---|
| A — already archived | **30 days** (2026-06-07) | At least one **real-hardware** demo run has been completed since 2026-05-08 with the four `docs/0[1-4]` documents as the only operator reference. No requests to restore an archived file. |
| B — confirmed-unused, in active tree | **60 days** (2026-07-07) | Owner sign-off recorded in commit message; build + dry-run + frontend build re-verified after each batch. |
| C — roadmap decision required | **No fixed date** | Decided by the package owner (`cobot_safety`/`cobot_policy`/`nuts_data_recording` → maintainer; `cobot_config/*.yaml` → calibration owner; `experiments/cobot_OD_obb_small/` → ML lead). Do not delete on a clock alone. |
| D — Firebase tooling caches | **Now-safe** to `git rm --cached` (not `rm`); the `.gitignore` already covers them. | The `.gitignore` change from the previous step must be committed first. |
| E — stale install-tree | **Now-safe** to `rm -rf build/ install/ log/` (local-disk only). | None — this is reversible by `colcon build`. |

**Hard rule**: do not delete *anything* that fails any of the
following pre-checks at deletion time:

1. `colcon build --symlink-install` finishes clean.
2. Mock dry-run from `docs/03_run_manual.md` §5.2 reaches `[state] done`.
3. `npm run build` in `web_stt_firebase/` succeeds.
4. `grep -RnE "<basename>" cobot_*/ conveyor_controller/ scripts/ web_stt_firebase/src/ docs/0*.md` returns zero hits for each path being deleted.

If any of these fails, halt and re-evaluate.

---

## 7. Exact deletion commands (do **not** run from this document)

The following are the literal shell commands you would use when each
gate is met. They are presented as reference, **not** to be executed by
this proposal.

### Tier A — after 2026-06-07, all conditions in §6 met

```bash
# Operate from workspace root
cd ~/cobot2_ws

# Re-verify before deletion
colcon build --symlink-install
ros2 launch cobot_robot_control robot_control.launch.py &  # one terminal
ros2 run  cobot_perception mock_perception_node            &  # another
ros2 run  cobot_task_manager task_manager_node             &  # another
# Watch for [state] done in the task_manager terminal, then ^C all three

# Tier A deletions
git rm  _archive_cleanup/20260508/web_stt_firebase/STEPS2WEBinLOCAL.md
git rm  _archive_cleanup/20260508/experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv
git rm  _archive_cleanup/20260508/experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv
git rm  _archive_cleanup/20260508/experiments/cobot_OD_obb_small/train_log.txt
git rm  _archive_cleanup/20260508/experiments/cobot_OD_obb_small/tune_log.txt

# Suggested commit
git commit -m "Tier A archive deletion: drop unused training logs and the local-setup memo"
```

`publish_robot_session_scenarios.py` is **not** in this list — it stays
archived per §3.

### Tier B — after owner sign-off

```bash
# Voice-processing legacy node (also remove the entry-point line from setup.py)
git rm cobot_voice/cobot_voice/voice_processing_node.py
# Then manually edit cobot_voice/setup.py and delete the line:
#   'voice_processing = cobot_voice.voice_processing_node:main',

# Top-level shims
git rm cobot_voice/keyword_extraction.py
git rm cobot_voice/voice_order_flow.py

# Unused cobot_config YAMLs
git rm cobot_config/config/handeye.yaml
git rm cobot_config/config/workspace.yaml
git rm cobot_config/config/slot_poses.yaml
git rm cobot_config/config/policy_config.yaml
git rm cobot_config/config/object_aliases.yaml

# Re-verify after each batch
colcon build --symlink-install
# Repeat the dry-run from Tier A.

git commit -m "Tier B: remove confirmed-unused legacy modules and reference YAMLs"
```

### Tier C — only after explicit roadmap decision

```bash
# Empty stub packages — only if the roadmap drops them
git rm -r cobot_safety/
git rm -r cobot_policy/

# Calibration tool — only after calibration-owner approval
git rm -r nuts_data_recording/

# bringup params.yaml — preferred path is to wire it in instead of removing
git rm cobot_bringup/config/params.yaml

# Alternative model variant — only after sustained nano-model stability
git rm -r experiments/cobot_OD_obb_small/

# Phase-1 training artifacts (both variants)
git rm -r experiments/cobot_OD_obb_nano/train_phase1_20260504_173049/
git rm -r experiments/cobot_OD_obb_small/train_phase1_20260505_203819/

git commit -m "Tier C: remove roadmap-resolved stubs and superseded experiment runs"
```

### Tier D — Firebase tooling caches (untrack, do not delete from disk)

```bash
# Pre-condition: the .gitignore additions from the previous step must be committed.
git rm --cached web_stt_firebase/.firebase/.graphqlrc
git rm --cached web_stt_firebase/.firebase/INSTRUCTIONS.md
git rm --cached web_stt_firebase/dataconnect/.dataconnect/schema/prelude.gql

git commit -m "Untrack Firebase tooling caches (regenerated by firebase-tools)"
```

### Tier E — stale install-tree artifacts (no git involvement)

```bash
# Local-disk hygiene only; no commit
rm -rf build/ install/ log/
colcon build --symlink-install
```

### Legacy docs migration (not deletion)

Before any decision to delete the seven legacy `docs/*.md` files,
prefer migration:

```bash
mkdir -p docs/_archive
git mv docs/run_manual.md                          docs/_archive/
git mv docs/voice_to_robot_integration_plan.md     docs/_archive/
git mv docs/three_firebase_bridge_changes.md       docs/_archive/
git mv docs/three_firebase_bridge_integration_test.md docs/_archive/
git mv docs/nut_recommendation_changes.md          docs/_archive/
git mv docs/nut_recommendation_flow.md             docs/_archive/
git mv docs/stt_db_tts_robot_integration.md       docs/_archive/

# Then update the "Document set" block in docs/01_system_architecture.md
# so the supersession note points at docs/_archive/.

git commit -m "Move superseded design docs to docs/_archive/"
```

---

## Summary in one paragraph

Six files have been safely archived to `_archive_cleanup/20260508/`
with `git mv`. The build, mock dry-run, and frontend build all pass
without them. **No file should be permanently deleted before
2026-06-07** at the earliest, and even then only items in Tier A.
Tiers B and C require explicit owner sign-off. Tier D (Firebase tooling
caches) and Tier E (stale install artifacts) are reversible local-only
or untrack-only operations and can proceed whenever the prior
`.gitignore` change is committed. `publish_robot_session_scenarios.py`
should remain archived indefinitely. The seven legacy docs are best
migrated to `docs/_archive/` rather than deleted. When in doubt, leave
the file archived — restoration is cheap, accidental loss is not.
