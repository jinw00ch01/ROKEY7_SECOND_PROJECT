# Nut Recommendation Flow

## Overview

The voice order flow converts a user's STT result into a nut combo order file that can be read by a future `robot_control` node or bridged into a ROS2 message.

Current runtime output:

```text
cobot_voice/output/latest_order.json
```

The robot side should only execute an order when `success` is `true`.

## Data Flow

```text
WakeupWord.is_wakeup()
  -> speak(wake_response)
  -> speak(ask_state)
  -> STT.speech2text() or debug input()
  -> extract_categories(state_text)
  -> retry once with retry_state if no category is found
  -> speak(ask_intensity)
  -> STT.speech2text() or debug input()
  -> extract_intensity(intensity_text)
  -> build_combo(categories, intensity)
  -> speak(confirm_template.format(combo_text=...))
  -> save latest_order.json
```

Main modules:

- `cobot_voice/cobot_voice/wakeup_word.py`: wake word detection.
- `cobot_voice/cobot_voice/stt.py`: microphone recording and STT text return.
- `cobot_voice/cobot_voice/nut_recommendation.py`: category extraction, intensity extraction, combo generation, and Korean combo text formatting.
- `cobot_voice/cobot_voice/question_flow.py`: TTS prompt message lookup from `config/question_flow.json`.
- `cobot_voice/cobot_voice/voice_order_flow.py`: end-to-end wake word, prompt, STT, retry, combo, confirmation, and save flow.
- `cobot_voice/cobot_voice/keyword_extractor.py`: writes the normalized JSON order file.

## JSON Schema

`latest_order.json` keeps this stable object shape:

```json
{
  "request_id": "YYYYMMDD_HHMMSS",
  "recognized_text": "피곤하고 집중이 안 돼요 많이",
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

Field contract:

- `request_id`: string timestamp in `YYYYMMDD_HHMMSS` format.
- `recognized_text`: full recognized user text used for the final recommendation.
- `categories`: list of extracted state category ids.
- `intensity`: one of `low`, `normal`, or `high`.
- `combo`: always a list.
- `combo[].nut`: English nut class name. Allowed values are `almond`, `cashew`, `pistachio`, `walnut`.
- `combo[].count`: integer count for that nut.
- `combo_text`: Korean TTS-ready summary string.
- `success`: boolean execution gate.

Combo count rule:

- `config/nut_combo_rules.json` defines `max_total_count`.
- If the generated combo exceeds `max_total_count`, later categories are treated as lower priority and reduced first.
- Duplicate nut entries are normalized by summing their counts.

## Execution Gate

`success=false` means the recommendation is incomplete and `robot_control` must not execute.

Cases that produce `success=false`:

- No category was extracted.
- No combo could be generated.
- `combo` is empty after schema normalization.

Recommended robot-side check:

```python
if not order.get("success"):
    return

for item in order.get("combo", []):
    nut = item["nut"]
    count = int(item["count"])
    # Execute only for allowed nut classes and positive counts.
```

## Example Failure Output

```json
{
  "request_id": "20260506_113200",
  "recognized_text": "그냥 괜찮아요",
  "categories": [],
  "intensity": "normal",
  "combo": [],
  "combo_text": "",
  "success": false
}
```

## Debug Run

Terminal input can be used without microphone or real TTS:

```bash
cd /home/aes/cobot2_ws/cobot_voice
python3 voice_order_flow.py --debug
```

The debug flow uses `input()` for STT and `print()` through `speak(text)` for TTS placeholders.
