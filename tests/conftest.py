import pytest
from webui.settings import ConfigFile
import webui
import tempfile
import os


def set_pcw_ini(filename, add=''):
    with open(filename, "w") as f:
        f.write(add)


@pytest.fixture(autouse=True)
def pcw_file():
    tmpFile = tempfile.mkstemp()
    webui.settings.CONFIG_FILE = tmpFile[1]
    set_pcw_ini(tmpFile[1])
    yield tmpFile[1]
    if os.path.exists(tmpFile[1]):
        os.remove(tmpFile[1])



