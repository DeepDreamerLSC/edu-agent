# AGENTS.md

本仓库只做两件事:小讲师 agent 与评测线(00 §1)。规则总纲两份,开工前通读:

- [docs/plan/02-complexity-budget.md](docs/plan/02-complexity-budget.md) —— 复杂度预算(第 2 节)、函数级度量(2.1)、包依赖方向(2.2)、测试边界(第 6 节)、落地保障(第 11 节)
- [docs/plan/04-deploy-and-integration.md](docs/plan/04-deploy-and-integration.md) —— PR 关卡与分支纪律(3.1)、三道 CI 关卡(3.2)、agent 提 PR 最低要求(3.7)

**提 PR 前 `make check` 必须绿**(等价于完整 PR CI;红灯在本地看,不推到远端)。

**ponytail(可选辅助,插件本体不进仓库、不进 CI)**:编码前默认启用 ponytail(full 档);不可用不阻塞,仍守最小修改原则。编码后、`make check` 前对完整 diff 执行一次 ponytail-review,合理的 delete/stdlib/native/yagni/shrink 建议直接处理。不设第二审查通道、不开生命周期 Hook;ponytail-debt 只读。

其余硬规则一句话版:agent 只开 PR 不合并;四类结构改动(顶层包、第三方依赖、配置文件、CI 规则/规划文档/`scripts/budget.py`)必须人批;不自建租约/心跳/worker 池/调度器/预载恢复(02 §5);预算超限没有豁免,要加就先删(02 §2)。
