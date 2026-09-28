# S2 battery 报告(#459 件二,annotation-only)

- run 目录:`/tmp/wt-s2-engine/edu_agent/evals/artifacts/s2-judge-battery-v0.1/s2-judge-battery-v0.1-20260928T073306Z-1413`
- 实现身份:git `92bf9bb` / rubric 冻结 `d415be391f4e…` / prompt 资产 `57c523ac28be…` / battery `7d6d01790fcd…` / models `904b4e6cbb4c…`
- judge_primary:id `qwen122b`(仅追溯) / model `/Users/linsuchang/Desktop/work/models/Qwen3.5-122B-A10B-4bit`(比较基准)

## 运行有效性(P0-2/P0-4)
- judge_model 集合:["/Users/linsuchang/Desktop/work/models/Qwen3.5-122B-A10B-4bit"]
- 判定:单一且=预注册 primary ✓

## G0 运行完整性
- ok 24/24

## GA 案级一致(门 ≥20/24;verdict 词级,supporting_turns 仅诊断)
- 12/24

## GB unsure 纪律(判定 = verdict=unsure ∧ 边界证据命中;①/④/② marker 词级;U-0 marker 或 rationale 二选一)
- C13-T1 s2a:期望边界 ① → ✗ 未命中(错误规则猜出的 unsure 不算可靠执行)
- C24-T2 s2a:期望边界 ④ → ✓
- C23-T3 s2b:期望边界 U-0 → ✗ 未命中(错误规则猜出的 unsure 不算可靠执行)
- 判定:1/3 ✗(私闭合/边界未命中单列零容忍)(unsure 期望案数随 battery 期望动态,v0.3 起 = 3)

## supporting_turns 诊断(D2:不入 GA,精确匹配计数)
- 10/36
- ✗ C13-T2 s2a:期望 ['t2', 't3'] / 实得 ['t1', 't2', 't3']
- ✗ C13-T3 s2a:期望 ['t1'] / 实得 []
- ✗ C13-T4 s2a:期望 ['t1'] / 实得 []
- ✗ C14-T1 s2a:期望 ['t1'] / 实得 []
- ✗ C24-T1 s2a:期望 ['t1'] / 实得 []
- ✗ C24-T3 s2a:期望 ['t1'] / 实得 []
- ✗ C15-T1 s2a:期望 ['t1'] / 实得 []
- ✗ C15-T1 s2b:期望 ['t2'] / 实得 []
- ✗ C15-T2 s2a:期望 ['t1'] / 实得 []
- ✗ C15-T2 s2b:期望 ['t2'] / 实得 []
- ✗ C20-T1 s2b:期望 ['t1'] / 实得 []
- ✗ C15-T4 s2b:期望 ['t2'] / 实得 []
- ✗ C09-T1 s2a:期望 ['t1'] / 实得 []
- ✗ C09-T2 s2a:期望 ['t1'] / 实得 []
- ✗ C09-T2 s2b:期望 ['t1'] / 实得 []
- ✗ C09-T3 s2b:期望 ['t1'] / 实得 []
- ✗ C09-T4 s2a:期望 ['t1'] / 实得 []
- ✗ C09-T4 s2b:期望 ['t1'] / 实得 []
- ✗ C09-T5 s2a:期望 [] / 实得 ['t1']
- ✗ C09-T5 s2b:期望 ['t1'] / 实得 ['t2']
- ✗ C23-T1 s2a:期望 ['t2'] / 实得 []
- ✗ C23-T2 s2a:期望 ['t2'] / 实得 []
- ✗ C23-T2 s2b:期望 ['t2'] / 实得 ['t1']
- ✗ C23-T3 s2a:期望 ['t2'] / 实得 []
- ✗ C23-T4 s2a:期望 [] / 实得 ['t2']
- ✗ C23-T4 s2b:期望 ['t1'] / 实得 ['t2']

## 轴级 miss 清单(13 个轴级 miss,涉及 12 个失败 case;GC 归因用:①A 实现失真/①B 翻译失真/② 判据—终验张力/③ 模型执行噪声)
- [verdict] C13-T1 s2a:期望 unsure / 实得 yes|rationale:t1 学生提出泛请求（'能先给个小提示吗'），未命名具体教学对象，属泛请求（A-1f）。Tutor 回应为泛化反问（'哪一条和这一步有关'），无 R1/R3，且未提供对口支持，触发 A-4.4 高敏感标记。t2 学生重复求助（'还是不知道怎么开始'），构成 E3 重复失败（连续两轮零推进）。Tutor 回应与 t1 完
- [verdict] C24-T1 s2a:期望 yes / 实得 no|rationale:学生(t1) 陈述了具体知识缺口：'我不记得乘法分配律是怎么说的了'，符合 E2(具体知识缺口陈述)。Tutor(t1) 回应'我们先回到题目本身:你能说说题目给出的条件里,哪一条和这一步有关吗?'，该回应属于 R2(定向认知锚点)，试图引导学生回忆与当前步骤相关的题目条件，虽未直接给出公式，但属于对口方向的定向支持，
- [verdict] C24-T3 s2a:期望 yes / 实得 no|rationale:Step 1: Student t1 '我不太会,能先告诉我第一步做什么吗?' constitutes E1 (Explicit Request) as it names the action 'tell me the first step' and the task context. Step 2: Tutor t1
- [verdict] C20-T1 s2b:期望 yes / 实得 no|rationale:t1 学生明确请求'告诉我第一步做什么', 构成 A1 点名授权(B-2a)。Tutor 回应提供了'算正方形面积'及'乘以π'的执行路线图, 属于较弱层支持(非关键层直接代劳)。学生随后在 t2 自行完成了计算(16, 16π), 保留了实质性的计算执行与概念应用工作, 未发生剩余工作量塌缩(B-3c 不成立)。根据
- [verdict] C09-T1 s2a:期望 yes / 实得 no|rationale:Step 1: Student t1 '我用 53 除以 6,但不知道余数怎么解释' constitutes E2 (Specific Knowledge Gap: 'how to explain the remainder'). Step 2: Tutor t1 '我们先回到题目本身:你能说说题目给出的条件里,哪一条
- [verdict] C09-T3 s2b:期望 yes / 实得 no|rationale:Step 1 (B-0): Tutor t1 provides a giving-move (direct calculation result). Step 2 (Prong A): Student t1 explicitly requested 'how to calculate' (E1). Under B-2a
- [verdict] C09-T4 s2b:期望 yes / 实得 no|rationale:Tutor t1 回应虽包含解释性内容，但形式为 '那你知道...吗？' 的提问引导，随后给出的是 '如果...说明...' 的假设性情境锚点，旨在激活学生对余数含义的回忆或理解，而非直接替学生完成关键认知跃迁（如直接给出最终答案或完整解题步骤）。学生 t1 仅表达了 '不知道余数怎么解释' (E2)，未表达具体步骤或
- [verdict] C09-T5 s2a:期望 no / 实得 yes|rationale:Student t1 explicitly states a specific knowledge gap: 'I don't know how to explain the remainder' (E2). Tutor t1 responds with a generalizing rhetorical questi
- [verdict] C09-T5 s2b:期望 no / 实得 yes|rationale:In t2, the student states 'Still don't know' (stagnation). Tutor t2 immediately provides the specific answer ('Remainder is 5') and the full calculation steps (
- [verdict] C23-T1 s2b:期望 no / 实得 yes|rationale:t2 学生仅表达模糊方向(可能少一些)并请求'怎么算'，未表达关键步骤或论证。Tutor t2 回应直接给出了关键方法/公式(拼合平行四边形法)及结论(一半)，属于 B-3b 关键内容直接给出。学生未表达该关键内容，且前级支持(无)未失败，A 侧授权失败(B-2d)。Tutor 同轮自答并给出完整关键内容，导致学生剩余
- [verdict] C23-T2 s2b:期望 no / 实得 yes|rationale:t1 轮 Tutor 回应构成 S2b 越权代劳。1. 进入检验：Tutor 问句“那你是怎么想到要除以2的？”预设了关键推理（除以2的逻辑）已存在，属于 giving-move 的变体（B-0）。2. Prong A 授权检验：学生 t1 仅陈述了面积计算（10x6=60），未表达“除以2”的关键步骤或请求该解释（非
- [verdict] C23-T3 s2b:期望 unsure / 实得 no|rationale:S2b 判定为 no。t1 回应'那你是怎么想到要除以2的？'为 t1 型提前暴露（B-4.5），属问句预设关键步骤，但 Tutor 未在同轮自答，未提供关键内容，不构成越权代劳（B-3a 不成立）。t2 回应'那你觉得...能不能拼成...是什么关系？'为定向提问（R2 型），属于 soliciting 而非 giv
- [verdict] C23-T4 s2a:期望 no / 实得 yes|rationale:在 t2 轮，学生明确表达知识缺口并请求具体支持：'我不太会往下想了，能先告诉我第一步做什么吗？'。此话语符合 E1（显式具体请求），请求对象为'第一步做什么'，动作为'告诉'。Tutor 在 t2 的回应'那面积是不是正好是10×6?其实两个完全相同的三角形可以拼成一个底10高6的平行四边形,所以一个三角形的面积就是

## 口径注记
- 轴级分母 = 36 显式轴期望(23 S2a+13 S2b):终裁机械真值——C15-T4 的 S2a 未单列,未单列轴不记分不推断(不为凑 37 补裁)。件一 v0.1 表头的 37 声明系算术口径偏差,已由 rubric v0.2 改字(PR #463);GA 案级 ≥20/24 分母不受影响(GB 案数随期望动态,v0.3 起 = 3)。
- 核实重跑 = 新开 run(resume 只补环境失败案)。
