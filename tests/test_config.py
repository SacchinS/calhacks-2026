"""config.yaml loading: the demo overlay keeps main on mock."""

from shared.config import load_config


def test_overlay_config_sets_real_components_on_top_of_config_yaml():
    config = load_config(overlay="config.demo.yaml")
    assert (config.recognizer, config.translator, config.claude_code) == (
        "camera",
        "claude",
        "real",
    )
    assert (config.siri, config.tts, config.captions) == ("real", "cartesia", "cartesia")
    assert config.get("audio.virtual_mic_device") == "BlackHole 2ch"  # the rest is config.yaml's
    assert load_config().tts == "mock"  # main stays on mock
