# edu-agent

小讲师（Small Lecturer）教学对话 agent 与其评测线路的重写仓库。

本仓库是对 Gitee 上 `edu_agent` 单体仓库的**提炼重写**：只保留一条产品线（小讲师）和一条工程主线（评测），
其余业务域不迁移。重写的核心是**模型调用链路的效率与稳定性**。

- 重写计划：[docs/plan/00-rewrite-plan.md](docs/plan/00-rewrite-plan.md)
- 模型调用链路设计：[docs/plan/01-model-call-chain.md](docs/plan/01-model-call-chain.md)
- 复杂度预算：[docs/plan/02-complexity-budget.md](docs/plan/02-complexity-budget.md)
- 整体架构图：[docs/plan/03-architecture.md](docs/plan/03-architecture.md)

老仓库进入冻结维护状态，继续为合作方提供现有接口，直到本仓库在评测上追平并完成接口对齐。
