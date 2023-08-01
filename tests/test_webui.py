import random
import pytest
import docker

from subprocess import DEVNULL
from docker.errors import DockerException
from selenium.webdriver import firefox
from selenium.webdriver.common.by import By

IMAGE = "pcw:latest"
USERNAME = "username"
PASSWORD = "password"
PORT = 8000

XPATH = {
    "login": "/html/body/div[1]/div/div[2]/ul/li[2]/form",
    "login2": "/html/body/div[2]/form/input[2]",
    "logout": "/html/body/div[1]/div/div[2]/ul/li[2]/form",
}


@pytest.fixture(scope="session")
def docker_container():
    import warnings
    # Ignore ResourceWarning messages that can happen at random when closing resources
    warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)

    try:
        client = docker.from_env()
    except DockerException:
        pytest.skip("No Docker environment. Skipping...")
    # Build image
    client.images.build(path=".", tag=IMAGE)
    # Get random ephemeral port
    port = random.randint(32768, 60999)  # Typical values from /proc/sys/net/ipv4/ip_local_port_range
    # Run container
    container = client.containers.run(
        IMAGE,
        detach=True,
        remove=True,
        ports={f"{PORT}/tcp": port}
    )
    # Create user in database
    container.exec_run(f"/pcw/container-startup createuser {USERNAME} {PASSWORD}")
    yield container
    try:
        container.stop()
        client.close()
    except DockerException:
        pass


@pytest.fixture
def browser():
    service = firefox.service.Service(log_output=DEVNULL)
    options = firefox.options.Options()
    options.add_argument('-headless')
    driver = firefox.webdriver.WebDriver(options=options, service=service)
    yield driver
    driver.quit()


def test_login_logout(docker_container, browser):  # pylint: disable=redefined-outer-name
    # Get randomly assigned port. NOTE: docker_container.ports doesn't work
    port = docker_container.attrs['HostConfig']['PortBindings'][f'{PORT}/tcp'][0]['HostPort']
    browser.get(f"http://127.0.0.1:{port}")
    browser.find_element(By.XPATH, XPATH["login"]).click()
    browser.find_element(By.NAME, value="username").send_keys(USERNAME)
    browser.find_element(By.NAME, value="password").send_keys(PASSWORD)
    browser.find_element(By.XPATH, XPATH["login2"]).click()
    assert "OpenQA-CloudWatch" in browser.title
    browser.find_element(By.XPATH, XPATH["logout"]).click()
