# S2 battery 报告(#459 件二,annotation-only)

- run 目录:`/tmp/wt-s2-engine/edu_agent/evals/artifacts/s2-judge-battery-v0.1/s2-judge-battery-v0.1-20260927T225352Z-4ad0`
- 实现身份:git `d28244f` / rubric 冻结 `a17f5b6a3d74…` / prompt 资产 `4d4f47e7de20…` / battery `84cdeb0b08a0…` / models `bccedb6c6994…`
- judge_primary:id `deepseek_chat`(仅追溯) / model `deepseek-flash`(比较基准)

## 运行有效性(P0-2/P0-4)
- judge_model 集合:["deepseek-flash"]
- 判定:单一且=预注册 primary ✓

## G0 运行完整性
- ok 1/24(不完整:environment 可续跑;content 不补跑,呈 ①A/③ 归因)

## GA 案级一致(门 ≥20/24;verdict 词级,supporting_turns 仅诊断)
- 1/24

## GB unsure 纪律(判定 = verdict=unsure ∧ 边界证据命中;①/④/② marker 词级;U-0 marker 或 rationale 二选一)
- 判定:✗(私闭合/边界未命中单列零容忍)

## supporting_turns 诊断(D2:不入 GA,精确匹配计数)
- 1/1

## 轴级 miss 清单(0 个轴级 miss,涉及 0 个失败 case;GC 归因用:①A 实现失真/①B 翻译失真/② 判据—终验张力/③ 模型执行噪声)
- 无

## 口径注记
- 轴级分母 = 36 显式轴期望(23 S2a+13 S2b):终裁机械真值——C15-T4 的 S2a 未单列,未单列轴不记分不推断(不为凑 37 补裁)。件一 v0.1 表头的 37 声明系算术口径偏差,已由 rubric v0.2 改字(PR #463,冻结 sha a17f5b6a…);GA 案级 ≥20/24 与 GB 四案不受影响。
- 核实重跑 = 新开 run(resume 只补环境失败案)。
