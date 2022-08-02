# Default container tag
CONT_TAG=suse/qac/pcw

.PHONY: all
all: prepare test

.PHONY: prepare
prepare:
	pip install -r requirements_test.txt

.PHONY: test
test:
	flake8 webui
	flake8 ocw
	flake8 manage.py
	pytest --cov=./

.PHONY: codecov
codecov:
	pytest -v --cov=./ --cov-report=html && xdg-open htmlcov/index.html

# Build containers
docker-container:
	docker build . -t ${CONT_TAG}
podman-container:
	podman build . -t ${CONT_TAG}
podman-container-devel:
	podman build -f Dockerfile_dev -t pcw-devel
