from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.yaml"
JOB_LIST_MODES = {"vision", "dom"}


def load_config():
    with CONFIG_PATH.open(encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def test_config_declares_the_vision_job_list_mode_by_default():
    config = load_config()

    assert config["extraction"]["job_list_mode"] == "vision"


def test_config_job_list_mode_is_limited_to_supported_values():
    config = load_config()

    assert config["extraction"]["job_list_mode"] in JOB_LIST_MODES
