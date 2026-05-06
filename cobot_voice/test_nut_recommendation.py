import tempfile
from pathlib import Path

from cobot_voice.keyword_extractor import normalize_combo
from cobot_voice.nut_recommendation import build_combo, load_json, recommend_nuts


def _combo_count_by_nut(result):
    return {item["nut"]: item["count"] for item in result["combo"]}


def test_fatigue_focus_high():
    result = recommend_nuts("너무 피곤하고 집중이 잘 안 돼요")
    combo = _combo_count_by_nut(result)

    assert result["categories"] == ["fatigue", "focus"]
    assert result["intensity"] == "high"
    assert "cashew" in combo
    assert "walnut" in combo


def test_blood_sugar_diet():
    result = recommend_nuts("혈당이 걱정되고 다이어트 중이에요")
    combo = _combo_count_by_nut(result)

    assert result["categories"] == ["blood_sugar", "diet"]
    assert "almond" in combo
    assert "pistachio" in combo


def test_no_categories():
    result = recommend_nuts("그냥 괜찮아요")

    assert result["categories"] == []
    assert result["combo"] == []


def test_low_fatigue():
    result = recommend_nuts("조금 피곤해요")
    combo = _combo_count_by_nut(result)

    assert result["intensity"] == "low"
    assert combo["cashew"] == 1


def test_empty_text():
    result = recommend_nuts("")

    assert result["recognized_text"] == ""
    assert result["categories"] == []
    assert result["intensity"] == "normal"
    assert result["combo"] == []


def test_unknown_intensity_defaults_to_normal():
    categories_config = {
        "categories": {
            "fatigue": {
                "nut": "cashew",
            }
        }
    }
    combo_rules = {
        "intensity_counts": {
            "low": 1,
            "normal": 2,
            "high": 3,
        },
        "max_total_count": 6,
    }

    combo = build_combo(["fatigue"], "unknown", combo_rules, categories_config)

    assert combo == [{"nut": "cashew", "count": 2}]


def test_max_total_count_caps_by_priority():
    categories_config = {
        "categories": {
            "fatigue": {"nut": "cashew"},
            "focus": {"nut": "walnut"},
            "diet": {"nut": "pistachio"},
        }
    }
    combo_rules = {
        "intensity_counts": {
            "high": 3,
            "normal": 2,
        },
        "max_total_count": 4,
    }

    combo = build_combo(
        ["fatigue", "focus", "diet"],
        "high",
        combo_rules,
        categories_config,
    )
    combo_by_nut = _combo_count_by_nut({"combo": combo})

    assert sum(combo_by_nut.values()) == 4
    assert combo_by_nut["cashew"] == 3
    assert combo_by_nut["walnut"] == 1
    assert "pistachio" not in combo_by_nut


def test_duplicate_nut_counts_are_summed():
    combo = normalize_combo(
        [
            {"nut": "cashew", "count": 1},
            {"nut": "cashew", "count": "2"},
            {"nut": "unknown", "count": 10},
        ]
    )

    assert combo == [{"nut": "cashew", "count": 3}]


def test_missing_json_error_includes_path():
    missing_path = Path("/tmp/cobot_voice_missing_config.json")

    try:
        load_json(missing_path)
    except FileNotFoundError as exc:
        assert str(missing_path) in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError")


def test_invalid_json_error_includes_path():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=True) as file:
        file.write("{invalid")
        file.flush()

        try:
            load_json(file.name)
        except ValueError as exc:
            assert file.name in str(exc)
        else:
            raise AssertionError("Expected ValueError")


def main():
    test_fatigue_focus_high()
    test_blood_sugar_diet()
    test_no_categories()
    test_low_fatigue()
    test_empty_text()
    test_unknown_intensity_defaults_to_normal()
    test_max_total_count_caps_by_priority()
    test_duplicate_nut_counts_are_summed()
    test_missing_json_error_includes_path()
    test_invalid_json_error_includes_path()
    print("All tests passed.")


if __name__ == "__main__":
    main()
