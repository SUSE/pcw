# Default container tag
CONT_TAG=suse/qac/pcw
LINE_MAX=140
FILES=ocw/lib/*.py ocw/management/commands/*.py ocw/*.py *.py

.PHONY: all
all: prepare flake8 test pylint

.PHONY: prepare
prepare:
	pip install -r requirements_test.txt

.PHONY: pylint
pylint:
	pylint $(FILES)

.PHONY: flake8
flake8:
	flake8 --max-line-length=$(LINE_MAX) $(FILES) tests/*.py

.PHONY: test
test:
	pytest --cov

.PHONY: codecov
codecov:
	pytest -v --cov --cov-report=html && xdg-open htmlcov/index.html

# Build containers
container:
	podman build . -t ${CONT_TAG} -f containers/Dockerfile
container-base:
	podman build . -t ${CONT_TAG}-base -f containers/Dockerfile_base
container-base-k8s:
	podman build . -t ${CONT_TAG}-base-k8s -f containers/Dockerfile_base_k8s
container-devel:
	podman build . -t ${CONT_TAG}-devel -f containers/Dockerfile_dev
container-k8s:
	podman build . -t ${CONT_TAG}-k8s-cleaner -f containers/Dockerfile_k8s
container-k8s-devel:
	podman build . -t ${CONT_TAG}-k8s-cleaner-devel -f containers/Dockerfile_k8s_dev

# Container linting
.PHONY: container-lint
container-lint: containers/Dockerfile*
	hadolint containers/Dockerfile*
