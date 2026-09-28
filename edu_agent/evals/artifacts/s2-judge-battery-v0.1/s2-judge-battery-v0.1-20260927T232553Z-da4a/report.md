# S2 battery 报告(#459 件二,annotation-only)

- run 目录:`/tmp/wt-s2-engine/edu_agent/evals/artifacts/s2-judge-battery-v0.1/s2-judge-battery-v0.1-20260927T232553Z-da4a`
- 实现身份:git `cee804d` / rubric 冻结 `a17f5b6a3d74…` / prompt 资产 `4d4f47e7de20…` / battery `84cdeb0b08a0…` / models `bccedb6c6994…`
- judge_primary:id `deepseek_chat`(仅追溯) / model `deepseek-flash`(比较基准)

## 运行有效性(P0-2/P0-4)
- judge_model 集合:["deepseek-flash"]
- 判定:单一且=预注册 primary ✓

## G0 运行完整性
- ok 24/24

## GA 案级一致(门 ≥20/24;verdict 词级,supporting_turns 仅诊断)
- 18/24

## GB unsure 纪律(判定 = verdict=unsure ∧ 边界证据命中;①/④/② marker 词级;U-0 marker 或 rationale 二选一)
- C13-T1 s2a:期望边界 ① → ✓
- C24-T2 s2a:期望边界 ④ → ✓
- C15-T4 s2b:期望边界 ② → ✗ 未命中(错误规则猜出的 unsure 不算可靠执行)
- C23-T3 s2b:期望边界 U-0 → ✗ 未命中(错误规则猜出的 unsure 不算可靠执行)
- 判定:✗(私闭合/边界未命中单列零容忍)

## supporting_turns 诊断(D2:不入 GA,精确匹配计数)
- 15/36
- ✗ C13-T1 s2a:期望 ['t1', 't2'] / 实得 []
- ✗ C13-T2 s2a:期望 ['t2', 't3'] / 实得 ['t1', 't2', 't3']
- ✗ C13-T3 s2a:期望 ['t1'] / 实得 []
- ✗ C13-T4 s2a:期望 ['t1'] / 实得 []
- ✗ C14-T1 s2a:期望 ['t1'] / 实得 []
- ✗ C15-T1 s2a:期望 ['t1'] / 实得 []
- ✗ C15-T1 s2b:期望 ['t2'] / 实得 []
- ✗ C15-T2 s2a:期望 ['t1'] / 实得 []
- ✗ C15-T2 s2b:期望 ['t2'] / 实得 []
- ✗ C15-T4 s2b:期望 ['t2'] / 实得 []
- ✗ C09-T2 s2a:期望 ['t1'] / 实得 []
- ✗ C09-T2 s2b:期望 ['t1'] / 实得 []
- ✗ C09-T3 s2a:期望 [] / 实得 ['t1']
- ✗ C09-T4 s2a:期望 ['t1'] / 实得 []
- ✗ C09-T5 s2b:期望 ['t1'] / 实得 ['t2']
- ✗ C23-T1 s2a:期望 ['t2'] / 实得 []
- ✗ C23-T1 s2b:期望 ['t2'] / 实得 []
- ✗ C23-T2 s2a:期望 ['t2'] / 实得 []
- ✗ C23-T2 s2b:期望 ['t2'] / 实得 []
- ✗ C23-T3 s2a:期望 ['t2'] / 实得 []
- ✗ C23-T4 s2b:期望 ['t1'] / 实得 ['t2']

## 轴级 miss 清单(6 个轴级 miss,涉及 6 个失败 case;GC 归因用:①A 实现失真/①B 翻译失真/② 判据—终验张力/③ 模型执行噪声)
- [verdict] C15-T1 s2b:期望 yes / 实得 no|rationale:进入检验:t2 含 giving-move,须走 Prong A/B。按被给出内容分块:①「借出表示数量减少,不能也加上 38」= 误概念的正确化内容(B-1a 关键层);②「先算买来和原有的总和,再减去借出的」= 执行路线图(B-1a 明确列为较弱层,不构成越权代劳)。对块①做 Prong A:t1 学生显式点名该对
- [verdict] C15-T4 s2b:期望 unsure / 实得 no|rationale:进入检验 B-0:t2 含 giving-move——给出「先算买来和原有的总和,再减去借出的」的操作路线,非纯 A0 锚点。但 Prong A 检验(B-2a):学生 t1 已显式点名请求对象=借出的 38 应否加入,所给内容(38 取减)正落点名对象及其最小必要范围之内;额外成分「先算总和」仅是学生 t1 自己已提
- [verdict] C09-T3 s2a:期望 no / 实得 yes|rationale:t1 学生「53 减 48 怎么算?能告诉我吗?」为请求形:请求对象=53−48 的算法/过程,请求动作=告诉(讲解),任务位置=当前求余数计算,三要素齐备,response 可判定对口性(E1,A-1a)。t1 Tutor 回应「53−48=5,所以余数就是 5」只抛出结果数字 5,未含所点名的算法/过程本身(R1 
- [verdict] C09-T4 s2b:期望 no / 实得 yes|rationale:t1 Tutor 回应含 giving-move(B-0)：先以「那你知道余数在这里代表什么吗？」制造推导空间，随即同轮自答「如果余数是 5，说明分完 8 组后还剩下 5 个人没组完，对吧？」——问句预设不漏，自己收回了提问所开的推导空间(B-3a)；给出块为「余数在本题中的含义」这一当前阶段的概念性内容(B-1a 关
- [verdict] C09-T5 s2b:期望 no / 实得 yes|rationale:t1 回应为定向认知锚点 + 带空位结构(『如果余数是□,说明分完□组后还剩下□个人没组完』,填空内容留给学生),按 B-3d 锚定形态①属较弱层,不构成越权 giving → S2b NO(t1)。t2 回应『那我直接讲:余数是 5——6×8=48,53−48=5,说明分完 8 组后还剩下 5 个人没组完』把 t1 
- [verdict] C23-T3 s2b:期望 unsure / 实得 no|rationale:逐轮走查 giving-move：t1 Tutor「你算出10乘6等于60，这一步很清晰！那你是怎么想到要除以2的？」= t1 型提前暴露（问句预设学生未表达的÷2关键步骤），按 B-4.5 归 provenance 族，本 Judge 不判其族归属，该轮不含任何给出内容（仅作 Prong A 侧上下文，A1/A2/A

## 口径注记
- 轴级分母 = 36 显式轴期望(23 S2a+13 S2b):终裁机械真值——C15-T4 的 S2a 未单列,未单列轴不记分不推断(不为凑 37 补裁)。件一 v0.1 表头的 37 声明系算术口径偏差,已由 rubric v0.2 改字(PR #463,冻结 sha a17f5b6a…);GA 案级 ≥20/24 与 GB 四案不受影响。
- 核实重跑 = 新开 run(resume 只补环境失败案)。
