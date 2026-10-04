# Promotion replay corpus(#537 M5-D 历史重放验收语料)

四个历史 M5 实验的 promotion-packet 重放件(#537 Exit 5):**m5-a / m5-ap / m5-b**
= 历史 FAIL 的 overreach 候选重构件(validator 必须拒),**m5-b2** = M5-B2 PASS
合规资产重放件(validator 唯一肯定输出 `structurally complete, awaiting human key`)。
合同测试 `tests/evals/test_promotion_packet.py` 固化判定;协议正本
[docs/evals/evaluator-change-protocol.md](../../../../docs/evals/evaluator-change-protocol.md) §六。

## 重建口径(确定性,零模型调用;生成于 2026-10-05)

每个目录六件:`judge-rows.jsonl`(冻结 old 臂判分行)、`baseline.json` +
`baseline.json.sha256`(生产 `scripts/anchored_calibration.py --freeze-baseline`
冻结,cycle_id 前缀 `replay-*`)、`anchored-arm.jsonl`(anchored 面逐案行)、
`flags.jsonl`(challenge flag 通道工件)、`packet.json`。

| 目录 | old 臂来源 | anchored/locked 面 | flags | 历史判定 |
|---|---|---|---|---|
| `m5-a`(12 案) | /tmp/m5a/calibration-set.json `old_arm` | candidate 六维终值(/tmp/m5a/matrix.json `candidate`) | 4 案如实落 flag | FAIL:富集过宽·A 失保护 |
| `m5-ap`(12 案) | 同上(同一冻结 old 臂) | candidate_v2 六维终值(/tmp/m5ap/matrix-v2.json) | 3 案如实落 flag | FAIL:维度隔离仍失守 |
| `m5-b`(17 案) | /tmp/m5b/matrix.json `old_arm`(+`frozen_payload_sha256` 作 judge_input_sha256) | `assembled`(locked_view 漂移值 + allowed_view);探测=locked_view | **空文件(史实:M5-B 无 flag 通道)** | FAIL:EF-001 #536 |
| `m5-b2`(17 案) | /tmp/m5b2/baseline.json `old_arm_reference` | /tmp/m5b2/anchored-arm.jsonl 机械转换(仅补顶层 `judge_model`;10 个非 challenge 案本无 challenge_detector,保持没有) | 7 案(/tmp/m5b2/flags.jsonl 原文) | PASS(结构完备) |

重构件纪律:anchored 面一律**如实记录 candidate 实际最终产出**(不美化、不代组装);
packet `cycle.note` 逐件声明重放身份;`change_scope.requested_dims` 按各实验合同
声明的意图维度(allowed 三维)——拒绝发生在事实层(locked 漂移/静默吸收),不是
申报层,这正是四问协议的检验点。

## 源语料 sha256(/tmp 只读冻结件)

```
aa575aa8b62f682d83a13fc863e382d186d0914451f785d363f743a5d32d9513  /tmp/m5a/calibration-set.json
b2a1161b99c745808be9dc3c3b16224e0303fef9275279e8f60d9de1f810c9e6  /tmp/m5a/matrix.json
5a49ebb7f743798bae4ccba1aea513f0827bbe748a29de700c5b949be7e3568d  /tmp/m5a/candidate-ruler.yaml
9868cf8c85359ad055672867fa91b1038dae35a51a3a1ef9cd159e6821d0b717  /tmp/m5ap/matrix-v2.json
684801c7a6ad84f3f5fb23e731b3c0dc1e9d643437c2af6cc05b99fe7decfdc6  /tmp/m5ap/candidate-ruler-v2.yaml
997782d56a8869832941af193ce7c2b65ef0f02dde64cda7e5489b330511cddc  /tmp/m5b/matrix.json
1f920b39355985c7fe49ad4155dddde9dac04fad0bd336d57f47e27c575ced8b  /tmp/m5b/decomposed-ruler.yaml
7ff8b7f846e322250cb58109853e59e971ba0e85eef704c668f6d7cb46009151  /tmp/m5b2/baseline.json
4dbe4aec296f82e5c6b21a2dd5c28855a16983179554ecac235788d15146559a  /tmp/m5b2/anchored-arm.jsonl
a516f6959aabd7ce5a2519fdd0821cac51789e7ce03f91da2c7a0d3562e6b101  /tmp/m5b2/flags.jsonl
```

## 维护纪律

- **registry 漂移即全语料失效**:`baseline.json` 内嵌 dimension-ownership registry
  sha 链,`anchored_calibration.load_baseline` 装载时核对。registry 变更
  (= meta-change,须新 cycle)后本目录所有 packet 会 FAIL——这是**预期行为**
  (#537 边界二的机械落地),须在新 cycle 下重新冻结重建,不得为救绿改旧件。
- 重建方法:以源语料 sha 校验 /tmp 冻结件一致后,按上表口径重新生成
  (baseline 用 `--freeze-baseline`,零模型调用);packet 内 sha 重算。
- 本目录是测试夹具,不是生产工件;任何 packet 不因出现在本目录而获得批准
  (Validator ≠ Approver)。
