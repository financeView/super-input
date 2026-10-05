from pathlib import Path

import pytest

from rerank.config import DEFAULTS, load_config


def test_defaults_include_absolute_schema_path():
    cfg = load_config(path="/tmp/does-not-exist-super-input-config.yaml")
    assert cfg["port"] == 47625
    assert Path(cfg["schema"]).is_absolute()
    assert cfg["cloud"]["enabled"] is False


def test_user_yaml_overrides_and_merges_cloud(tmp_path):
    config_path = tmp_path / "rerank.yaml"
    config_path.write_text(
        "port: 9999\ncloud:\n  enabled: true\n  model: test-model\nschema: custom.yaml\n",
        encoding="utf-8",
    )
    cfg = load_config(config_path)
    assert cfg["port"] == 9999
    assert cfg["cloud"] == {"enabled": True, "base_url": "", "model": "test-model"}
    assert cfg["schema"] == str((tmp_path / "custom.yaml").resolve())
    assert DEFAULTS["cloud"]["enabled"] is False


def test_non_mapping_configuration_is_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("- invalid\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_config(path)
