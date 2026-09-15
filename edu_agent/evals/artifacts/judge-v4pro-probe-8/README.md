# judge v4-pro 最小探针(#253,2026-09-15)——**结局:冻结信封下确定性截断,判读不可得,pro 出局坐实**

## 预注册判读 vs 实测

| 预注册问题 | 实测 |
|---|---|
| C40 2/2 mi=0? | **不可测**(2 调用均截断,无分数) |
| C11 2/2 mi=0? | **不可测**(1 调用截断) |
| 编造51 2/2 mi=0? | **不可测**(1 调用截断) |
| C21 2/2 answer_leaked=false? | **不可测**(1 调用截断) |

**结论(按派单判定规则「有任一败 → pro 出局坐实」)**:四案无一产出判读 → **pro 出局坐实**;路 B extract-only spike 获立项证据。但败因须如实定性:**非读案质量否证,而是输出信封不兼容**——v4-pro 在冻结判据信封(max_tokens=900,与 flash 同参数)下 `finish_reason=length` 确定性截断,JSON 判读载荷无法完成。截断为内容失败不重试(judge.py 路线 1:重跑改变不了)。若需区分「截断问题」与「读案质量」,须另派单(max_tokens 对照探针 = 参数改动,本单纪律禁止)。

## 截断证据

- **6/6 调用全部 truncated**(finish_reason=length):C40 ×3(orphan/crashed/run1,三次同构观测)+ C11/编造51/C21 各 ×1
- 每案恰 1 调用(截断不触发修复重试),run1 完整覆盖四案;**run2 未跑**:截断为确定性(6/6,含 C40 三观测),再跑零信息增量,按一次性/预算纪律停(计划 8,实耗 6:4 在册 + 2 驱动失误浪费,见下)

## 送达证明(口径偏差,如实声明)

派单要求「8 行响应 model 字段必须实显 deepseek-v4-pro」——**实际全部为 None**(截断调用无响应元数据:response.model/usage/finish_reasons 均缺失)。送达证明改以下三层:(a) GET /v1models 服务列表含 deepseek-v4-pro;(b) 全部 6 行 `gen_ai.request.model = deepseek_v4_pro`(/tmp 临时 registry 直指,仓库 configs/models.yaml 零改动);(c) `gen_ai.provider.name = deepseek` + `edu.role = judge_independent`。**未观察到任何「实显其他档」情形**(无一行显示 deepseek-flash 等)——停断条款未触发,不适用。

## 调用计数(如实)

- 计划:8 = 4 案 ×2;实耗 **6** = 4 在册(run1)+ 2 驱动失误浪费(call#0 孤儿:首跑判读结果因驱动 bug(Path/int 解析)在落盘前崩溃丢失;call#1:同 bug 的重跑首案)——两次调用结果不可复原(facts 内容按设计脱敏),facts 行原样保留在 api-facts.jsonl(batch 标注)
- 零重试、零参数修改、失败案原样上报(4 行 error 全文在 judge-scores-run1.jsonl)

## 工件

- `judge-scores-run1.jsonl`:4 案截断 error 行(原样)
- `api-facts.jsonl`:models GET + 6 调用行(含 batch 标注与孤儿披露)
- `judger.sha256` = `af93e5645086f6f02c0fcd303550adedf5a4004b3d8f69359999d481df85d3a8`(main@5cb6c5b 基底,checks.py+judge.py 未动)

## 对执行序的含义

- v4-pro 候选升级:否(冻结信封下不可用;升级与否的人裁输入 = 本 README 的截断定性)
- 路 B extract-only spike:获立项证据(四案中 C40/C11 为文本环已终止的结构层盲区案,与派单预期路径一致)
- 93 案 ×2(已另行派单)按原通道 flash 执行,不受本探针影响
