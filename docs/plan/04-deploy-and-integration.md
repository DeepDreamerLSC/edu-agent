# 04 部署与集成：两分钟部署，合并即验证

状态：草案（2026-09-06）。

## 1. 老仓库的两个症状

**部署半小时以上，且反复试错。** `scripts/deploy-backend.sh` 3342 行，一次部署串行执行：三套环境边界校验、
要求 git 工作区干净、迁移前备份、迁移、灌种子数据、重绑 prompt lab 版本、审计 promotion、等 Postgres、
等健康、登录 smoke、prompt lab 就绪、小讲师链路就绪、tutor 网关 smoke、题图渲染门禁、素材编辑门禁、
镜像身份校验、蓝绿槽位切换、回滚基线快照。另有 491 行脚本重启模型 worker，27B 权重重新加载数分钟。
任何一步因与本次改动无关的域失败，从头再来。

根因两个：**部署单位是整个平台**；**改一行应用代码要重载模型权重**。

**单 PR 都绿，合起来坏。** `/private/tmp` 下二十多个并行 worktree 各挂一条 feature 分支；本地有
`local-preview-211-212` 分支专门把两个 PR 合起来预览。集成检验发生在合并之后、靠人工。CI 只跑 PR 分支自身，
测试耦合实现而非行为，两个各自合理的 PR 语义冲突时没有任何东西会红。

## 2. 部署：三种变化速度分开

| 对象 | 变化频率 | 重启代价 | 部署方式 |
|---|---|---|---|
| 应用代码（gateway、agents、api） | 每天 | 秒 | `make deploy ENV=test` |
| 模型服务进程（mlx-lm server、llama-server） | 数周 | 分钟 | `make models-up / models-down / models-status` |
| 数据与配置（datasets、models.yaml、.env） | 随时 | 无 | 文件，随代码走或单独同步 |

gateway 是 HTTP 客户端，应用重启不碰模型进程。模型服务起来后跨应用部署一直活着。

### 2.1 应用部署规则

- 一条命令，目标 **两分钟内**：拉代码、`uv sync`、重启 launchd 服务、打健康检查、跑 smoke。
- v1 在 Mac 上不用 Docker。迁 Linux 时再引入，且只容器化应用，不容器化模型服务。
- 每一步幂等，失败重跑从断点继续。不要求工作区干净。`--dry-run` 打印计划。
- 环境只有 **local** 和 **test** 两个，同一条命令，只差一个 `.env`。没有 prod，直到合作方正式上线。
- 回滚 = 切回上一个 sha 重启。v1 无 schema；M3 的 store 只允许 additive 迁移。
- 部署脚本 **上限 100 行**，进 `scripts/budget.py`。
- 每次部署写一条 JSONL：deploy_id、sha、env、duration_ms、result。p95 超过三分钟视为缺陷。

### 2.2 只有一个健康检查和一个 smoke

- `GET /healthz` 返回：git sha、models.yaml 哈希、各上游 `/v1/models` 是否可达、进程启动时间。
- smoke = 拿 3 条固定评测用例打真实部署的端点，断言成功且教学合同关键断言通过。
- 合计一分钟内。各域的就绪门禁不进部署脚本，它们是 CI 里的测试。

## 3. 集成：合并即验证

### 3.1 主干开发

- 分支活不过 **两天**。CI 检查 PR 首个提交距今时间，超过打 `stale-branch` 标签并阻止合并，需 rebase。
  该检查在执行机制 PR 合并后启用，M0 第一个 PR 自身豁免。
- 每条 agent 线同时打开的 PR **不超过两个**，两条线（评测线 / gateway 与模型服务线）共四个。
- 一个 PR 触碰的顶层包 **不超过两个**。范围约束，不是体积约束：M0 建 gateway 骨架可以两千行，但只在 gateway 里。
- PR 行数是软信号：超过 800 行 CI 打 `large-pr` 标签，不阻塞，要求描述里写一句为什么必须一起合。
  M2 后若 `large-pr` 成常态再讨论收紧。

### 3.2 三道 CI 关卡

| 关卡 | 何时 | 跑什么 | 红了怎么办 |
|---|---|---|---|
| PR CI | 每次 push | ruff、import-linter、budget、单测、三类合同测试、黄金路径 e2e | 不能合 |
| 合并前重跑 | 合并按钮 | 程序性：agent 按 3.7 rebase 到最新 main 重跑；人合并前确认 checks 绿（分支保护在 GitHub Free 私有仓库不可用） | 先 rebase |
| main CI | 每次合并后 | 完整 PR CI + gateway 效率基准 vs 上次基线（01 文档第 5 节，20 条回放）+ 20 条评测冒烟 + 自动部署 test | 只允许 fix 或 revert PR；30 分钟不修好就 revert |

第二道关卡是消灭"各自绿、合起来红"最便宜的手段。注：分支保护与规则集在 GitHub Free
私有仓库不可用，此关卡目前为程序性约定（升级 Pro 后补开 strict 状态检查即恢复技术强制）；
第三道关卡（main 推送验证）因此前移为主要的兜底。

### 3.3 黄金路径端到端测试

每个 PR 跑一次：开会话 → 首问 → 两轮追问 → 结束出总结。走真实 api（M3 前走内核）、gateway、假上游。
跨模块语义冲突在这里暴露。用例固定，改动它需要在 PR 描述里单独说明。

### 3.4 评测是集成门

main CI 的 20 条评测冒烟与上次基线比：教学指标或效率指标劣化超过 01 文档阈值，自动开 issue、阻止部署。
"每个 PR 都对但合起来教学质量下滑"只有这一层能抓到。

### 3.5 test 环境永远等于 main HEAD

main CI 绿即自动部署 test。合起来有问题在几分钟内看到，不是几周后手工部署时才发现。
这依赖第 2 节把部署压到两分钟。

### 3.6 禁止 feature flag

v1 禁止 feature flag。开关是组合状态爆炸的第一来源。需要的差异只能在 models.yaml 里以角色配置表达。

### 3.7 agent 提 PR 的最低要求

- 提 PR 前 rebase 到 main 并重跑本地测试。
- PR 描述写明基于哪个 main sha 测的、需求来源、删除了什么。
- agent 不合并。合并即人批。

## 4. M0 落地清单

- [ ] `Makefile`：deploy、models-up/down/status、smoke、healthz 四组目标
- [ ] `scripts/deploy.sh` ≤ 100 行，幂等，`--dry-run`
- [ ] launchd plist 两份：应用、模型服务
- [ ] `GET /healthz` 实现
- [ ] `tests/e2e/test_golden_path.py`
- [x] GitHub 分支保护：**GitHub Free 私有仓库不可用**（升级 Pro 后补开 strict 状态检查 + 禁止直推）；以程序性约定替代，见 02 第 7 节
- [ ] main 推送报警（无分支保护的补偿，提前自 3.2 节）：push 到 main 的 CI 失败自动开 issue，合并后 30 分钟内未修复则人工 revert
- [ ] `.github/workflows/main.yml`：合并后评测冒烟 + 自动部署 test。评测冒烟与部署都需要能访问本机模型服务与 test 环境，
      因此在 Mac 上跑一个 **GitHub self-hosted runner**，PR CI 仍用托管 runner
- [ ] `scripts/budget.py` 增加：部署脚本行数、PR 触碰包数、分支年龄、`large-pr` 软标签
