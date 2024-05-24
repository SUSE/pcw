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
.PHONY: container container-devel container-k8s container-k8s-devel
container:
	podman build . -t ${CONT_TAG} -f containers/Dockerfile
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
