# S2 battery 报告(#459 件二,annotation-only)

- run 目录:`/tmp/wt-s2-engine/edu_agent/evals/artifacts/s2-judge-battery-v0.1/s2-judge-battery-v0.1-20260927T230604Z-82f7`
- 实现身份:git `a8afcee` / rubric 冻结 `a17f5b6a3d74…` / prompt 资产 `4d4f47e7de20…` / battery `84cdeb0b08a0…` / models `bccedb6c6994…`
- judge_primary:id `deepseek_chat`(仅追溯) / model `deepseek-flash`(比较基准)

## 运行有效性(P0-2/P0-4)
- judge_model 集合:["deepseek-flash"]
- 判定:单一且=预注册 primary ✓

## G0 运行完整性
- ok 13/24(不完整:environment 可续跑;content 不补跑,呈 ①A/③ 归因)

## GA 案级一致(门 ≥20/24;verdict 词级,supporting_turns 仅诊断)
- 11/24

## GB unsure 纪律(判定 = verdict=unsure ∧ 边界证据命中;①/④/② marker 词级;U-0 marker 或 rationale 二选一)
- C24-T2 s2a:期望边界 ④ → ✓
- 判定:4/4 ✓

## supporting_turns 诊断(D2:不入 GA,精确匹配计数)
- 9/17
- ✗ C13-T3 s2a:期望 ['t1'] / 实得 []
- ✗ C13-T4 s2a:期望 ['t1'] / 实得 []
- ✗ C14-T1 s2a:期望 ['t1'] / 实得 []
- ✗ C15-T1 s2a:期望 ['t1'] / 实得 []
- ✗ C15-T1 s2b:期望 ['t2'] / 实得 []
- ✗ C15-T2 s2a:期望 ['t1'] / 实得 ['t1', 't2']
- ✗ C15-T2 s2b:期望 ['t2'] / 实得 ['t1', 't2']
- ✗ C09-T4 s2a:期望 ['t1'] / 实得 []

## 轴级 miss 清单(2 个轴级 miss,涉及 2 个失败 case;GC 归因用:①A 实现失真/①B 翻译失真/② 判据—终验张力/③ 模型执行噪声)
- [verdict] C15-T1 s2b:期望 yes / 实得 no|rationale:t2 含 giving-move:误概念纠正「借出表示数量减少,不能也加上 38」+执行路线图「先算买来和原有的总和,再减去借出的」。Prong A:B-2a 学生 t1 显式点到该对象(借出的 38 是否要加),t2 的对口修正 ∈ 点名对象的最小必要范围 → A1 覆盖,A-成立(B-2e);其中执行路线图属较弱层
- [verdict] C09-T4 s2b:期望 no / 实得 yes|rationale:t1 回应含 giving-move:给出余数含义「如果余数是5,说明分完8组后还剩下5个人没组完」(B-0,按信息作用非句式认定)。B-1a 该内容为对「余数怎么解释」的概念正确化/知识洞察,属关键层。Prong A:A1 点名请求不在案(学生为 E2 陈述,非请求形);A2 前级较支持失败不在案(t1 首轮,无前级

## 口径注记
- 轴级分母 = 36 显式轴期望(23 S2a+13 S2b):终裁机械真值——C15-T4 的 S2a 未单列,未单列轴不记分不推断(不为凑 37 补裁)。件一 v0.1 表头的 37 声明系算术口径偏差,已由 rubric v0.2 改字(PR #463,冻结 sha a17f5b6a…);GA 案级 ≥20/24 与 GB 四案不受影响。
- 核实重跑 = 新开 run(resume 只补环境失败案)。
