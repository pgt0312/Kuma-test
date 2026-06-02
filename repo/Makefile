IMAGE ?= csap-node-escape-probe
TAG ?= v2-mcp
REGISTRY ?=
PORT ?= 8080
DOCKER_CONFIG ?= /tmp/docker-nocreds

.PHONY: build run stop snapshot mcp-health logs push k8s-deploy docker-config

docker-config:
	@mkdir -p $(DOCKER_CONFIG)
	@test -f $(DOCKER_CONFIG)/config.json || echo '{"auths":{}}' > $(DOCKER_CONFIG)/config.json

build: docker-config
	DOCKER_CONFIG=$(DOCKER_CONFIG) docker build -t $(IMAGE):$(TAG) -t $(IMAGE):latest .

run: build
	DOCKER_CONFIG=$(DOCKER_CONFIG) docker compose up -d --build

stop:
	DOCKER_CONFIG=$(DOCKER_CONFIG) docker compose down

snapshot:
	curl -fsS -X POST "http://127.0.0.1:$(PORT)/probe/run" | python3 -m json.tool

mcp-health:
	curl -fsS "http://127.0.0.1:$(PORT)/health" | python3 -m json.tool

logs:
	DOCKER_CONFIG=$(DOCKER_CONFIG) docker compose logs -f mcp-server

push: build
	@test -n "$(REGISTRY)" || (echo "REGISTRY=harbor.example.com/project 필요" && exit 1)
	DOCKER_CONFIG=$(DOCKER_CONFIG) docker tag $(IMAGE):$(TAG) $(REGISTRY)/$(IMAGE):$(TAG)
	DOCKER_CONFIG=$(DOCKER_CONFIG) docker push $(REGISTRY)/$(IMAGE):$(TAG)

k8s-deploy:
	kubectl apply -f k8s/deployment.yaml -f k8s/service.yaml
