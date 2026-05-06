import json
import sys

from cobot_voice.keyword_extractor import DEFAULT_OUTPUT_PATH, save_latest_order


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 keyword_extraction.py "너무 피곤하고 집중이 안 돼요"')
        return 1

    text = " ".join(sys.argv[1:]).strip()
    order = save_latest_order(text)
    print(json.dumps(order, ensure_ascii=False, indent=2))
    print(f"Saved to {DEFAULT_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
