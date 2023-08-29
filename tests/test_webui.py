import contextlib
import json
import random
import os
import shutil
import sys
from subprocess import DEVNULL

import pytest
from podman import PodmanClient
from podman.errors import APIError, PodmanError
from selenium.webdriver import firefox
from selenium.webdriver.common.by import By

USERNAME = "username"
PASSWORD = "password"
PORT = 8000

XPATH = {
    "login": "/html/body/div[1]/div/div[2]/ul/li[2]/form",
    "login2": "/html/body/div[2]/form/input[2]",
    "logout": "/html/body/div[1]/div/div[2]/ul/li[2]/form",
}


@pytest.fixture(scope="session")
def client():
    if os.getenv("SKIP_SELENIUM"):
        pytest.skip("Skipping because SKIP_SELENIUM is set")

    if not shutil.which("geckodriver"):
        pytest.skip("Please install geckodriver in your PATH. Skipping...")

    try:
        client = PodmanClient()
    except (APIError, PodmanError) as exc:
        pytest.skip(f"Broken Podman environment: {exc}")
    if not client.info()["host"]["remoteSocket"]["exists"]:
        pytest.skip("Please run systemctl --user enable --now podman.socket")

    yield client

    client.close()


@pytest.fixture(scope="session")
def random_port():
    # Get random number for ephemeral port, container and image name
    # Typical values from /proc/sys/net/ipv4/ip_local_port_range
    return random.randint(32768, 60999)


@pytest.fixture(scope="session")
def image(random_port, client):
    image_name = f"pcw-test{random_port}"

    # Build image
    try:
        client.images.build(
            path=".",
            dockerfile="Dockerfile",
            tag=image_name,
        )
    except APIError as exc:
        pytest.skip(f"Broken Podman environment: {exc}")
    except PodmanError as exc:
        for log in exc.build_log:
            line = json.loads(log.decode("utf-8"))
            if line:
                print(line.get("stream"), file=sys.stderr, end="")
        pytest.fail(f"{exc}")

    yield image_name

    # Cleanup
    with contextlib.suppress(APIError, PodmanError):
        client.images.remove(image_name)


@pytest.fixture(scope="session")
def container(random_port, image, client):
    try:
        # Run container
        container = client.containers.run(
            image=image,
            name=image,
            detach=True,
            remove=True,
            ports={f"{PORT}/tcp": random_port}
        )
        # Create user in database
        container.exec_run(f"/pcw/container-startup createuser {USERNAME} {PASSWORD}")
    except (APIError, PodmanError) as exc:
        pytest.fail(f"{exc}")

    yield container

    # Cleanup
    with contextlib.suppress(APIError, PodmanError):
        container.stop()
    with contextlib.suppress(APIError, PodmanError):
        container.remove()


@pytest.fixture
def browser(container):
    service = firefox.service.Service(log_output=DEVNULL)
    options = firefox.options.Options()
    options.add_argument('-headless')
    driver = firefox.webdriver.WebDriver(options=options, service=service)
    yield driver
    driver.quit()


def test_login_logout(random_port, browser):  # pylint: disable=redefined-outer-name
    browser.get(f"http://127.0.0.1:{random_port}")
    browser.find_element(By.XPATH, XPATH["login"]).click()
    browser.find_element(By.NAME, value="username").send_keys(USERNAME)
    browser.find_element(By.NAME, value="password").send_keys(PASSWORD)
    browser.find_element(By.XPATH, XPATH["login2"]).click()
    assert "OpenQA-CloudWatch" in browser.title
    browser.find_element(By.XPATH, XPATH["logout"]).click()
