VERSION_FILE := VERSION
VERSION := $(shell cat $(VERSION_FILE))
IMAGE_NAME ?= pihole-sqlite-exporter

.PHONY: version bump-patch bump-minor bump-major tag push-tag release docker-build docker-tag docker-push docker-release

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
	@docker build -f docker/Dockerfile.alpine -t $(IMAGE_NAME):$(VERSION) .

docker-tag:
	@docker tag $(IMAGE_NAME):$(VERSION) $(IMAGE_NAME):latest

docker-push:
	@docker push $(IMAGE_NAME):$(VERSION)
	@docker push $(IMAGE_NAME):latest

docker-release: docker-build docker-tag docker-push
