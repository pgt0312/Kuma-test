IMAGE ?= csap-node-escape-probe
TAG ?= playmcp-git
REGISTRY ?=
PORT ?= 8000
DOCKER_CONFIG ?= /tmp/docker-nocreds

.PHONY: build run stop snapshot mcp-health logs push k8s-deploy apply-is check-is docker-config

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
	kubectl apply -f k8s/deployment-baseline.yaml -f k8s/service.yaml

# PlayMCP 모니터링 탭 — InferenceService 생성 (1번 원인 해결)
# 예: make apply-is NS=my-ns MCP_NAME=csap-node-escape-probe IMAGE=harbor.../csap-node-escape-probe:playmcp-git
apply-is:
	@test -n "$(NS)" && test -n "$(MCP_NAME)" || (echo "NS= and MCP_NAME= required" && exit 1)
	chmod +x scripts/apply-inferenceservice-for-playmcp.sh
	MCP_NAME="$(MCP_NAME)" NS="$(NS)" IMAGE="$(IMAGE)" REMOVE_DEPLOY="$(REMOVE_DEPLOY)" \
		./scripts/apply-inferenceservice-for-playmcp.sh

check-is:
	@test -n "$(NS)" && test -n "$(MCP_NAME)" || (echo "NS= and MCP_NAME= required" && exit 1)
	chmod +x ../scripts/check-playmcp-istio-monitoring.sh
	MCP_NAME="$(MCP_NAME)" NS="$(NS)" ../scripts/check-playmcp-istio-monitoring.sh
