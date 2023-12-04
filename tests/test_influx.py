from ocw.lib.influx import Influx


def test_influx_init():
    influx = Influx()
    assert hasattr(influx, "__client") is False
