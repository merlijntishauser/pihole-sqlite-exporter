VERSION_FILE := VERSION
VERSION := $(shell cat $(VERSION_FILE))
IMAGE_NAME ?= pihole-sqlite-exporter
IMAGE_TAG ?= $(VERSION)
DOCKER_IMAGE := $(IMAGE_NAME):$(IMAGE_TAG)
GIT_COMMIT ?= $(shell git rev-parse --short HEAD 2>/dev/null)

.PHONY: version bump-patch bump-minor bump-major tag push-tag release docker-build docker-tag docker-push docker-release docker-buildx docker-lint docker-scan docker-verify

version:
	@echo $(VERSION)

bump-patch:
	@python3 -c "from pathlib import Path; v=Path('VERSION').read_text().strip().split('.'); major,minor,patch=map(int,v); patch+=1; Path('VERSION').write_text(f'{major}.{minor}.{patch}\n')"

bump-minor:
	@python3 -c "from pathlib import Path; v=Path('VERSION').read_text().strip().split('.'); major,minor,patch=map(int,v); minor+=1; patch=0; Path('VERSION').write_text(f'{major}.{minor}.{patch}\n')"

bump-major:
	@python3 -c "from pathlib import Path; v=Path('VERSION').read_text().strip().split('.'); major,minor,patch=map(int,v); major+=1; minor=0; patch=0; Path('VERSION').write_text(f'{major}.{minor}.{patch}\n')"

tag:
	@git tag -a v$(VERSION) -m "v$(VERSION)"

push-tag:
	@git push origin v$(VERSION)

release: tag push-tag

docker-build:
	@docker build -f docker/Dockerfile.alpine --build-arg GIT_COMMIT=$(GIT_COMMIT) -t $(DOCKER_IMAGE) .

docker-tag:
	@docker tag $(DOCKER_IMAGE) $(IMAGE_NAME):latest

docker-push:
	@docker push $(DOCKER_IMAGE)
	@docker push $(IMAGE_NAME):latest

docker-release: docker-build docker-tag docker-push

docker-buildx:
	@docker buildx build --platform linux/amd64,linux/arm64 -f docker/Dockerfile.alpine --build-arg GIT_COMMIT=$(GIT_COMMIT) -t $(DOCKER_IMAGE) -t $(IMAGE_NAME):latest --push .

docker-lint:
	@docker run --rm -v /var/run/docker.sock:/var/run/docker.sock goodwithtech/dockle:latest $(DOCKER_IMAGE)

docker-scan:
	@docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image $(DOCKER_IMAGE)

docker-verify: docker-build docker-lint docker-scan
