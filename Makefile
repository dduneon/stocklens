IMAGE = ghcr.io/dduneon/stocklens

# ── 개발 PC (Mac) ──────────────────────────────────────────────────────────

# ghcr.io 로그인 (GitHub PAT 필요: Settings → Developer settings → PAT → write:packages)
login:
	echo $$GITHUB_TOKEN | docker login ghcr.io -u dduneon --password-stdin

# 현재 플랫폼(ARM64)만 빌드 & 로컬 확인용
build:
	docker build -t $(IMAGE):latest .

# 멀티플랫폼 빌드 + ghcr.io 푸시 (amd64 + arm64)
push:
	docker buildx build \
		--platform linux/amd64,linux/arm64 \
		--push \
		-t $(IMAGE):latest \
		.

# 버전 태그 붙여 푸시 (예: make push-tag TAG=v1.0.0)
push-tag:
	docker buildx build \
		--platform linux/amd64,linux/arm64 \
		--push \
		-t $(IMAGE):$(TAG) \
		-t $(IMAGE):latest \
		.

# ── 로컬 개발 ──────────────────────────────────────────────────────────────

dev-up:
	docker compose up -d

dev-down:
	docker compose down

dev-logs:
	docker compose logs -f backend

# ── 미니PC 배포 (SSH 원격 실행) ────────────────────────────────────────────
# MINIPC_HOST=192.168.x.x  또는  MINIPC_HOST=minipc.local

deploy:
	ssh $(MINIPC_HOST) "cd ~/stocklens && \
		docker compose -f docker-compose.prod.yml pull && \
		docker compose -f docker-compose.prod.yml up -d"

deploy-logs:
	ssh $(MINIPC_HOST) "docker logs -f stocklens_backend"
