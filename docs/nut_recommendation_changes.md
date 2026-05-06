# Nut Recommendation Changes

## Summary

This change adds a state-based nut recommendation flow to `cobot_voice`.

The new flow takes STT text, extracts user state categories and intensity, generates a nut combo, formats a Korean TTS confirmation message, and writes a normalized order JSON file for future robot-side integration.

Runtime output:

```text
cobot_voice/output/latest_order.json
```

## Added Files

- `cobot_voice/config/keyword_categories.json`
  - Maps user condition categories to keywords and recommended nut classes.
- `cobot_voice/config/nut_combo_rules.json`
  - Defines intensity counts, max total count, and combo overflow behavior.
- `cobot_voice/config/question_flow.json`
  - Defines TTS prompt strings.
- `cobot_voice/cobot_voice/nut_recommendation.py`
  - Extracts categories/intensity and builds combo recommendations.
- `cobot_voice/cobot_voice/question_flow.py`
  - Loads TTS prompt messages and formats templates.
- `cobot_voice/cobot_voice/voice_order_flow.py`
  - Orchestrates wake response, state question, retry, intensity question, combo creation, confirmation, and JSON save.
- `cobot_voice/keyword_extraction.py`
  - CLI wrapper for generating `latest_order.json` from one STT text string.
- `cobot_voice/voice_order_flow.py`
  - CLI wrapper for debug-mode interactive flow.
- `cobot_voice/test_nut_recommendation.py`
  - Pure Python assert tests for recommendation behavior.
- `cobot_voice/test_question_flow.py`
  - Pure Python assert tests for question flow messages.
- `docs/nut_recommendation_flow.md`
  - Data flow and JSON schema documentation.

## Modified Files

- `cobot_voice/cobot_voice/keyword_extractor.py`
  - Preserved existing `KeywordExtractor.extract()` behavior.
  - Added order-building and JSON-saving helpers.
  - Added schema normalization for `latest_order.json`.
- `cobot_voice/setup.py`
  - Includes `config/*.json` in ROS package install data.

## Main Functions

- `recommend_nuts(text)`
- `extract_categories(text, categories_config)`
- `extract_intensity(text)`
- `build_combo(categories, intensity, combo_rules, categories_config)`
- `format_combo_text(combo)`
- `load_question_flow()`
- `get_message(key, **kwargs)`
- `build_latest_order(text)`
- `save_latest_order(text)`
- `save_recommendation_order(recommendation)`
- `run_recommendation_flow(stt=None, wakeup=None, debug=False, wait_for_wake=True)`

## JSON Output Schema

`latest_order.json` uses this stable schema:

```json
{
  "request_id": "YYYYMMDD_HHMMSS",
  "recognized_text": "너무 피곤하고 집중이 안 돼요",
  "categories": ["fatigue", "focus"],
  "intensity": "high",
  "combo": [
    {
      "nut": "cashew",
      "count": 3
    },
    {
      "nut": "walnut",
      "count": 3
    }
  ],
  "combo_text": "캐슈넛 세 개와 호두 세 개",
  "success": true
}
```

Rules:

- `combo` is always a list.
- Each `combo` item contains `nut` and `count`.
- `nut` stays as an English class name: `almond`, `cashew`, `pistachio`, `walnut`.
- `count` is normalized to `int`.
- Duplicate nut items are merged by summing counts.
- `combo_text` is a Korean TTS-ready string.
- `success=false` means robot execution must not start.

## Error Handling

- Missing JSON config files raise an error with the missing file path.
- Invalid JSON raises an error with file path, line, and column.
- Empty STT text returns:

```json
{
  "categories": [],
  "intensity": "normal",
  "combo": [],
  "combo_text": "",
  "success": false
}
```

- Unknown intensity defaults to `normal`.
- Combo totals are capped by `max_total_count` using priority order.
- Logging is handled through Python `logging`; detailed logs are shown in debug mode.

## How To Run

Single text conversion:

```bash
cd /home/aes/cobot2_ws/cobot_voice
python3 keyword_extraction.py "너무 피곤하고 집중이 안 돼요"
```

Interactive debug flow:

```bash
cd /home/aes/cobot2_ws/cobot_voice
python3 voice_order_flow.py --debug
```

Tests:

```bash
cd /home/aes/cobot2_ws/cobot_voice
python3 test_nut_recommendation.py
python3 test_question_flow.py
```

Expected test output:

```text
All tests passed.
All question flow tests passed.
```

## Verified Cases

| Input | Categories | Intensity | Combo | Success |
|---|---|---|---|---|
| `너무 피곤하고 집중이 안 돼요` | `fatigue`, `focus` | `high` | `cashew`, `walnut` | `true` |
| `혈당도 걱정되고 다이어트 중이에요` | `blood_sugar`, `diet` | `normal` | `almond`, `pistachio` | `true` |
| `조금 피곤해요` | `fatigue` | `low` | `cashew: 1` | `true` |
| `괜찮아요` | empty | `normal` | empty | `false` |

## Next ROS2 Integration Work

- Decide whether `robot_control` reads `latest_order.json` directly or receives a ROS2 message.
- If using ROS2 messages, add a nut order message to `cobot_msgs`.
- Publish the normalized order only when `success=true`.
- In `robot_control`, ignore any order where `success=false`.
- Convert each combo item into robot tasks by `nut` class and `count`.
- Add completion/failure status publishing so voice/web layers can reflect robot state.
