"""Exercise the real cfg_dir tree shipped to users and the container lab."""
from pathlib import Path

from shinken.objects.config import Config


def test_shipped_configuration_parses_without_phantom_brokers():
    root = Path(__file__).resolve().parents[1]
    config = Config()
    config.read_config_silent = 1
    objects = config.read_config_buf(config.read_config([str(root / "etc/shinken.cfg")]))
    assert config.conf_is_correct
    assert [broker["broker_name"] for broker in objects["broker"]] == [["broker-master"]]
    assert all("broker_timeseries" not in module.get("module_type", [])
               for module in objects["module"])
