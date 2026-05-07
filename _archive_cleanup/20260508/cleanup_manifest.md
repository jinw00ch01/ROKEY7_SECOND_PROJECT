# Cleanup Archive — 2026-05-08

This folder holds files that were **moved** (not deleted) out of the
active repository tree on 2026-05-08 because reference verification
showed them to be unused, but the move was conservative:

- Moves were performed with `git mv` so history is preserved.
- Working-tree copies are intact under this directory.
- No source code, no ROS package directory, no launch / config / msg /
  srv / action file, no calibration file, no in-use model weight, and
  no file referenced by `docs/03_run_manual.md` or any operator script
  was moved.

If anything moved here turns out to be needed, restore with:

```bash
git mv _archive_cleanup/20260508/<archived-path> <original-path>
```

---

## 1. Moved files (6)

### `cobot_voice/scripts/publish_robot_session_scenarios.py`

| Field | Value |
|---|---|
| Original path | `cobot_voice/scripts/publish_robot_session_scenarios.py` |
| Archived path | `_archive_cleanup/20260508/cobot_voice/scripts/publish_robot_session_scenarios.py` |
| Reason | Standalone Firestore-state injector for demo scenarios. Not part of the production voice loop. |
| Evidence | (1) Not in `cobot_voice/setup.py` `console_scripts` (only `voice_processing`, `voice_web_demo`, `web_voice_bridge_server`, `firebase_status_bridge` are exposed). (2) `grep -RnE "publish_robot_session_scenarios"` across `cobot_*/`, `conveyor_controller/`, `scripts/`, `web_stt_firebase/src/`, `docs/0*.md` returns no hits outside the file itself. (3) Not imported by any other Python module. |
| Risk level | **low** |

### `web_stt_firebase/STEPS2WEBinLOCAL.md`

| Field | Value |
|---|---|
| Original path | `web_stt_firebase/STEPS2WEBinLOCAL.md` |
| Archived path | `_archive_cleanup/20260508/web_stt_firebase/STEPS2WEBinLOCAL.md` |
| Reason | 554-byte standalone local-setup memo. The web run-up procedure now lives in `docs/03_run_manual.md` §6.5. |
| Evidence | `grep -RnE "STEPS2WEBinLOCAL"` returns no hits outside the file itself. Not referenced by `web_stt_firebase/README.md`, `firebase.json`, `package.json`, or any of `docs/01..04`. |
| Risk level | **low** |

### `experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv`

| Field | Value |
|---|---|
| Original path | `experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv` |
| Archived path | `_archive_cleanup/20260508/experiments/cobot_OD_obb_nano/conf_sweep_20260504_175042.csv` |
| Reason | YOLO confidence-threshold sweep output (CSV). Not loaded by any runtime code; pure historical artifact. |
| Evidence | `grep -RnE "conf_sweep"` across all source dirs and `docs/0*.md` returns 0 hits. |
| Risk level | **low** |

### `experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv`

| Field | Value |
|---|---|
| Original path | `experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv` |
| Archived path | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/conf_sweep_20260505_231450.csv` |
| Reason | Same as nano variant: YOLO confidence-threshold sweep output. |
| Evidence | Same `grep` returns 0 hits. The "small" model is not the production model anyway (production is `train_phase2_20260504_173049/weights/best.pt` in `cobot_OD_obb_nano`). |
| Risk level | **low** |

### `experiments/cobot_OD_obb_small/train_log.txt`

| Field | Value |
|---|---|
| Original path | `experiments/cobot_OD_obb_small/train_log.txt` |
| Archived path | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/train_log.txt` |
| Reason | 908 KB stdout log from a one-off YOLO training run. Pure historical artifact. |
| Evidence | `grep -RnE "train_log\.txt"` returns 0 hits across source dirs and active docs. |
| Risk level | **low** |

### `experiments/cobot_OD_obb_small/tune_log.txt`

| Field | Value |
|---|---|
| Original path | `experiments/cobot_OD_obb_small/tune_log.txt` |
| Archived path | `_archive_cleanup/20260508/experiments/cobot_OD_obb_small/tune_log.txt` |
| Reason | 40 KB stdout log from `inference_tune.py` runs. |
| Evidence | `grep -RnE "tune_log\.txt"` returns 0 hits. |
| Risk level | **low** |

---

## 2. Files explicitly NOT moved (deferred per the rules)

The following appeared in the prior cleanup report as "confirmed unused"
but were **kept in the active tree** because the user-supplied rules
exclude them by category. They remain candidates for a follow-up pass
that requires explicit owner sign-off.

| Path | Why it was kept |
|---|---|
| `cobot_config/config/handeye.yaml` | Rule 3 (config file) and rule 4 (calibration file). Even though no runtime loader reads it, its content is calibration values and removing it would erase the documented reference. |
| `cobot_config/config/workspace.yaml` | Rule 3 (config file). |
| `cobot_config/config/slot_poses.yaml` | Rule 3 (config file). |
| `cobot_config/config/policy_config.yaml` | Rule 3 (config file). |
| `cobot_config/config/object_aliases.yaml` | Rule 3 (config file). |
| `cobot_bringup/config/params.yaml` | Rule 3 (config file). Documented as currently not loaded by any launch; the recommendation is to wire it in rather than archive it. |
| `cobot_safety/` (whole package) | Rule 2 (ROS package directory). Empty stubs only, but the package layout is preserved per the rule. |
| `cobot_policy/` (whole package) | Rule 2 (ROS package directory). |
| `nuts_data_recording/` (whole package) | Rule 2 (ROS package directory). Calibration tool — needs owner sign-off before any move. |
| `cobot_voice/cobot_voice/voice_processing_node.py` and the `voice_processing` entry point | Rule 1 (active source code — though documented as legacy, it builds and installs as part of `cobot_voice`). |
| `cobot_voice/keyword_extraction.py`, `cobot_voice/voice_order_flow.py` (top-level shims) | Rule 1 (in-package source). |
| `experiments/cobot_OD_obb_*/{analyze_dataset.py, inference_tune.py, merge_datasets.py, split_dataset.py, visualize_results.py, yolo_train.py}` | Re-training utilities — keeping them in place lets a future re-training session run from the experiments dir without restoring from this archive. |
| `experiments/cobot_OD_obb_*/train_phase1_2026*/{args.yaml,results.csv}` | `args.yaml` resembles a config file (rule 3 stricter reading); `results.csv` is paired with it. Phase-1 training is superseded by phase-2 but the artifacts are kept together. |
| `experiments/cobot_OD_obb_*/{data.yaml, data_extra.yaml, dataset_stats.json, experiment_03.md, experiment_04.md}` | `data*.yaml` are training data manifests (rule 3 broad reading); the `experiment_*.md` files are explicitly named in the root `.gitignore` (line 22). |
| `web_stt_firebase/.firebase/.graphqlrc`, `INSTRUCTIONS.md`, `web_stt_firebase/dataconnect/.dataconnect/schema/prelude.gql` | These are now `.gitignore`-matched but currently still in the index. The recommended action (per the prior `.gitignore` update step) is `git rm --cached <path>` — they should be untracked, not archived. **No move performed here.** |
| Legacy `docs/{run_manual,voice_to_robot_integration_plan,three_firebase_bridge_*,nut_recommendation_*,stt_db_tts_robot_integration}.md` | Out of scope for this pass — they live under `docs/` which we already established as the canonical doc root; the proposed `docs/_archive/` migration is a separate planned step. |

---

## 3. Notes

- All six moves used `git mv`, so `git log --follow <archived path>` will
  show the file's full pre-move history.
- Total disk reclaimed in the active tree by these moves: ~960 KB
  (mostly the two log files).
- This archive directory is itself **not** added to `.gitignore` —
  intentional, so the moved files remain version-controlled in their
  new location.
- If a follow-up commit decides any of these files should be deleted
  outright, that is a separate operation; this directory is intended
  to live in tree until then.
