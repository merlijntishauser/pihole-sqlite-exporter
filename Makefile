VERSION_FILE := VERSION
VERSION := $(shell cat $(VERSION_FILE))
IMAGE_NAME ?= pihole-sqlite-exporter
IMAGE_TAG ?= $(VERSION)
DOCKER_IMAGE := $(IMAGE_NAME):$(IMAGE_TAG)
GIT_COMMIT ?= $(shell git rev-parse --short HEAD 2>/dev/null)

.PHONY: version version-bump docker-buildx docker-verify docker-redeploy tag-move

version:
	@echo $(VERSION)

version-bump:
	@current=$$(cat $(VERSION_FILE)); \
	default=$$(python3 -c 'import sys; v=sys.argv[1].strip().split("."); \
		(len(v)==3 and all(p.isdigit() for p in v)) or sys.exit(1); \
		major,minor,patch=map(int,v); patch+=1; \
		print(f"{major}.{minor}.{patch}")' "$$current"); \
	echo "Current version: $$current"; \
	read -p "New version [$$default]: " next; \
	if [ -z "$$next" ]; then next="$$default"; fi; \
	if ! echo "$$next" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$'; then \
		echo "Invalid semver (expected x.y.z)"; exit 1; \
	fi; \
	if ! git diff --quiet || ! git diff --cached --quiet; then \
		echo "Working tree not clean. Commit or stash changes first."; exit 1; \
	fi; \
	printf "%s\n" "$$next" > $(VERSION_FILE); \
	printf "__version__ = \"%s\"\n" "$$next" > src/pihole_sqlite_exporter/__init__.py; \
	git add $(VERSION_FILE) src/pihole_sqlite_exporter/__init__.py; \
	git commit -m "Bump version to $$next"; \
	git tag -a "v$$next" -m "v$$next"; \
	git push origin HEAD; \
	git push origin "v$$next"

docker-buildx:
	@docker buildx build --platform linux/amd64,linux/arm64 -f docker/Dockerfile.alpine --build-arg GIT_COMMIT=$(GIT_COMMIT) -t $(DOCKER_IMAGE) -t $(IMAGE_NAME):latest --push .

docker-verify:
	@docker build -f docker/Dockerfile.alpine --build-arg GIT_COMMIT=$(GIT_COMMIT) -t $(DOCKER_IMAGE) .
	@docker run --rm -v /var/run/docker.sock:/var/run/docker.sock goodwithtech/dockle:latest $(DOCKER_IMAGE)
	@docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image $(DOCKER_IMAGE)

docker-redeploy:
	@command -v gh >/dev/null 2>&1 || { echo "gh CLI is required"; exit 1; }
	@gh workflow run docker-release.yml --ref v$(VERSION)

tag-move:
	@read -p "Move tag v$(VERSION) to current HEAD? This rewrites history. [y/N]: " ans; \
	if [ "$$ans" != "y" ] && [ "$$ans" != "Y" ]; then \
		echo "Aborted."; exit 1; \
	fi; \
	git tag -f v$(VERSION); \
	git push origin -f v$(VERSION); \
	$(MAKE) docker-redeploy
