# r6 解析失败差异统计（MODEL_RESPONSE_PARSE_FAILED 归因）

方法：对 r6 全部 16 个 `question_image_understanding` 失败样本，取逐题证据中
记录的最终模型原始输出（`evidence.raw_output.raw_text`，即重试后的最终响应），
分三层重放：JSON 语法解析 → #206 v1 合同谓词（`question_image_output_contract`
的封闭 15 键骨架校验）→ 标准解析路径（`executor.execute`，与运行时同参数）。

## 结果：模型输出合规，解析器与合同不一致

| 层 | 结果 |
| --- | --- |
| JSON 语法 | 16/16 合法 JSON 对象 |
| v1 合同骨架（15 键封闭、类型） | 16/16 通过；无缺键、无多键、无键名错 |
| 标准解析路径（运行时同参数重放） | 16/16 复现失败 |

15/16 的唯一失败原因（pydantic ValidationError）：

```
('visual_evidence', N, 'evidence_type') literal_error:
Input should be 'table' | 'diagram' | 'graph' | 'geometry_figure' | 'chart' | 'other'
```

根因链：#206 合同把 `g[].m`（图形依赖描述）定义为**自由文本 string**；
解析层 `_normalize_visual_evidence_type`（compiler.py）的中文别名表未覆盖
模型实际输出的描述词，未命中时**原样透传**（`aliases.get(value, value)`），
导致中文文本进入仅接受 6 个英文枚举值的 `evidence_type` 字段。

高频未命中值（`g[].m` 实际输出统计）：`线段图`×4、`四分之一圆`×3、
`圆环`、`大圆减小圆`、`长方形图`、`方位角图`、`方格坐标系`、`圆与直角三角形`、
`四边形`、`四个圆`、`算术运算题`、`圆形花坛`、`线段图示意`、`半圆`、`text`。
现有别名表已覆盖"坐标系/几何图/示意图"等约 35 个词，但不含上述值。

剩余 1 例为 `CompactCompilePayloadError`（6a631186，compile 载荷问题，个例）。

## guided decoding（strict 约束）有效性

- r6 全部 24 次真实图片调用的原始输出 100% 为合法 JSON 且 15 键齐全
  （含全部 16 个被拒样本）——输出面完全满足合同骨架。
- 直接 A/B 探测（同 prompt 带/不带 `response_format`）在简单文本样本上
  无法区分（prompt 本身已足够强），未做穷举验证。
- 对本清单的结论无影响：瓶颈不在模型输出合规性，在解析器的枚举映射。

## 结论与下一步

**回答"模型不遵守 schema 还是解析器与合同不一致"：是后者。**
16 个失败中 15 个的模型输出在合同层完全合规，被拒的唯一原因是
`g[].m → evidence_type` 的归一化缺口。

修复方向（独立代码 PR，不属于本证据 PR 范围）：
1. `_normalize_visual_evidence_type` 未命中别名时降级为 `"other"`
   （fail-open 到兜底枚举，而非透传必然非法的原文）；或
2. 扩充高频别名（线段图→diagram、圆环→geometry_figure 等）并保留
   `"other"` 兜底。

预期：该单项修复后，r6 同清单 understanding 通过率应从 7/24 恢复到
约 21/24（7 通过 + 15 项归因于该缺口；另 1 例 compile 载荷与 1 例
队列超时除外），该预期需在修复后重跑验证。

## 修复验证（2026-09-02 postfix 运行）

修复（别名扩充 + 未命中兜底 `other`，compiler.py 净零行数变化）后同清单
复跑：`question_image_understanding` **24/24 全部通过**（本分析预测约
21/24，实测超预期——前次 blocked 的 5 题也全部通过），16 个解析失败
清零。证据见 `../question-image-m0-silver24-20260902-r6-postfix/`。
