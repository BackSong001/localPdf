from app.settings import load_settings


def test_tc_llm_001_gemini_key_order_and_deduplication() -> None:
    settings = load_settings(
        {
            "GEMINI_API_KEY": "first",
            "GEMINI_API_KEY_2": "second",
            "GEMINI_API_KEY_1": "first",
            "GEMINI_API_KEY_3": "",
        }
    )

    assert settings.gemini_api_keys == ("first", "second")


def test_tc_llm_002_nvidia_key_order_and_deduplication() -> None:
    settings = load_settings(
        {
            "NVIDIA_API_KEY_3": "third",
            "NVIDIA_API_KEY_1": "first",
            "NVIDIA_API_KEY_2": "second",
            "NVIDIA_API_KEY_2_DUPLICATE": "ignored",
        }
    )

    assert settings.nvidia_api_keys == ("first", "second", "third")


def test_tc_fr_014_b_defaults_are_local_only() -> None:
    settings = load_settings({})

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.max_files == 1000
