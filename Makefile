# 提 PR 前必须全绿(02 §11.5:make check = 完整 PR CI 等价物)。
.PHONY: check test deploy models-up models-down models-status smoke healthz

check:
	uv run ruff check .
	uv run lint-imports
	uv run python scripts/budget.py
	uv run python scripts/check_infra_keywords.py
	uv run python scripts/check_test_imports.py
	uv run pytest

test:
	uv run pytest

# ---- 部署与模型服务(04 §2):ENV 只有 local|test,差一个 .env.<ENV>,凭据不进仓库 ----

UID_S := $(shell id -u)
MODEL_LABELS := com.edu-agent.m0.mlx-tutor-8301 com.edu-agent.m0.llama-judge-8302
APP_URL := http://127.0.0.1:8300/healthz

deploy: ## 一条命令两分钟内(04 §2.1):make deploy ENV=local|test
	scripts/deploy.sh --env $(ENV)

models-up: ## 模型服务上线(幂等;plist 来自 deploy/launchd,#17 提供)
	@for label in $(MODEL_LABELS); do \
		launchctl bootstrap "gui/$(UID_S)" "deploy/launchd/$$label.plist" 2>/dev/null \
			&& echo "$$label: loaded" || echo "$$label: 已加载或 plist 缺失(#17),保持现状"; \
	done

models-down:
	@for label in $(MODEL_LABELS); do \
		launchctl bootout "gui/$(UID_S)/$$label" 2>/dev/null \
			&& echo "$$label: stopped" || echo "$$label: 未加载"; \
	done

models-status:
	@for label in $(MODEL_LABELS); do \
		launchctl print "gui/$(UID_S)/$$label" 2>/dev/null | grep -m1 "state = " \
			|| echo "$$label: not loaded"; \
	done

smoke:
	uv run python scripts/smoke.py

healthz:
	curl -fsS $(APP_URL)
