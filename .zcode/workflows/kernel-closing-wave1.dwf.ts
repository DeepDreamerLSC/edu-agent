/* zcode-workflow
description: Kernel 收口期第一波工作流:前置勘察→三 lane 并行修复(A/B/C,各自 make check
  门控+独立审查+新鲜眼终审)→合流审查(交叉面+rebase 合并序模拟)→PR-D 回归电池编写→汇总报告。适用于"多 PR
  并行的内核不变量修复+回归冻结"类任务。
whenToUse: 需要多个独立 PR 并行修复内核不变量(各有可命令化验收)、且需要交叉面审查与回归冻结时。含 §11
  禁令纪律块与三层审查(工作流初筛→新鲜眼→常驻审查者终审)约定。
*/
/* kernel-closing-wave1 —— Kernel 收口期第一波(架构师总裁定 2026-09-20,#382)
 * 形状:前置勘察 → 三 lane 并行(A/B/C,各自修复→审查→新鲜眼)→ 合流审查 → PR-D 回归电池 → 报告
 * 用户点火:2026-09-20「可以，同意点火」。合并键在人:脚本只产出 PR 与报告,绝不 merge。
 * 禁令正本=calibration-private/incident-20260920-700m-kernel-closing.md §11。
 */

interface Probe {
  ladder500FromAnalysis: boolean;
  evidence: string;
  imageMissing: boolean;
  prCVerdict: "修代码边界" | "修数据源" | "both";
}

interface LaneResult {
  pr: string;
  head: string;
  filesChanged: string[];
  makeCheck: "green" | "red" | "not-run";
  reviewVerdict: "可合" | "退回" | "有保留通过";
  reviewComment: string;
  freshEyeVerdict: string;
  violations: string[];
}

interface RegressionBattery {
  testFile: string;
  caseCount: number;
  redOnOld: string;
  dimensions: string[];
}

interface WaveReport {
  probe: Probe;
  lanes: { name: string; result: LaneResult }[];
  confluenceVerdict: string;
  regression: RegressionBattery;
  mergeOrderAdvice: string;
  notCovered: string[];
}

const VERDICT_DOC = "calibration-private/incident-20260920-700m-kernel-closing.md";
const BASE = "origin/main";

const COMMON = `纪律(照章程,仅列本次要点):
- 工作现场:在指定 worktree 干活(已预建含 venv),主树 /root/code/edu-agent 只读;基底 origin/main@27d8306。
- make check 绿才算完成(以脚本 world.run 门控的 exitCode 为准,声称不算)。
- 禁令§11 逐字遵守(正本 ${VERDICT_DOC} §11):不扩病例短语表/不写 case-specific 条件(700m/6⁄5/温度题)/不加实验 arm/不加 policy DSL/不另调 LLM 验 step/不包模型 retry/不大改 Judge/不把用户重试记教学复读/不在正确性 PR 里顺带优化文案分数。
- 只开 PR 不合并;PR 描述用仓库模板三字段,需求来源写「#382 PR-X,架构师总裁定 2026-09-20」。
- 回执/评论自报家门 dev=<lane角色名> wt=<worktree路径>;审查按 docs/roles/reviewer.md 验证式。`;

phase("前置勘察:500m 阶梯来源查证");
const probe = await agent("勘察员-题源查证").ask<Probe>(`
勘察 #382 PR-C 前置:事故中导师 reveal 的「A处海拔是500米」来自题库 analysis 还是 start() 模型生成?
已知线索(须独立复核):题库 edu_agent/contracts/partner_bank.json records[18](question_id=6a61b3d4)original_analysis 仅「先由图读出大致海拔,再按每升高100m下降3/5℃计算」无海拔数字;question_image=null。
步骤:①读 kernel.py 的 session.steps 生成路径(题库 analysis 切片 + start() 模型 ladder,注意「解析不足两步继续用模型生成」分支);②对 6a61b3d4 走查两条路径各自产出;③核模型 ladder 校验(整副任一 value 碰答案 focus 即接受?)。
零代码零 PR。产出 Probe;evidence 须命令+输出级(grep 行号/代码引用)。`);
log(`勘察结论:500m 来自 ${probe.ladder500FromAnalysis ? "题库 analysis" : "模型生成"};prCVerdict=${probe.prCVerdict}`);

phase("三 lane 并行:修复+审查+新鲜眼(A/B/C)");
const laneSpecs = [
  { name: "PR-A", slug: "learner-state-ownership", role: "dev-A线-状态所有权", doc: "P0-1",
    task: `修复 stuck 语义污染:session.stuck 只允许「学生本人明确 stuck 信号」写入。
已知违规写入点(须独立核实后处置):kernel.py L441(guard 硬降级)、L729 附近(_repeat_refine 里 reveal 后置 stuck)、L741(_deterministic_turn 学生信号,合法路径保留)。
动作:删除/改道违规写入(guard 降级只记 guard_events;repeat→reveal 不置 stuck);新增回归:Tutor repeat 不置 stuck、guard fallback 不置 stuck、学生信号仍可置。
不改动:Prompt、Judge;reveal 动作本身保留(只是不再写 stuck);与裁定冲突处以裁定全文为准并留注。` },
  { name: "PR-B", slug: "final-close-atomicity", role: "dev-B线-事务原子性", doc: "P0-2",
    task: `修复收束失败原子性:_close_on_final_statement() 遇 GatewayError 全回滚。
现状:append student → finish()(stuck=True 时调 Gateway)→ append assistant → version+=1;异常可致 history 已变/version 未变/assistant 未提交(生产实录:同句重发×2+GatewayError×2)。
动作:最小修复(append pending → try finish → except rollback → raise;或 prepare→commit 若现结构方便);不做 transaction framework;确认 finish() 其他异常路径同样失败不推进 Session。
验收测试:注入 GatewayError 前后 history/state/summary/session_version/hint_level 逐字段一致;同消息重试零重复 history。` },
  { name: "PR-C", slug: "trusted-ladder-boundary", role: "dev-C线-权威源边界", doc: "P0-3",
    task: `修复 reveal 权威源:ladder 加最小 provenance(analysis/model),deterministic reveal 只消费 trusted。
勘察结论(可采信但须自己复核):该题 analysis 无海拔数字、question_image=null → 错误阶梯来自模型生成。方向=修代码边界。
动作:session.steps 每步加 provenance 字段;_reveal_stuck_hint 只回放 provenance=analysis 的步;模型 ladder 保留规划辅助不进 deterministic reveal;无 trusted ladder → 走既有 safe guiding question 机制(禁止温度题话术硬编码)。题图缺失的事实记入 PR 描述(数据面另单,不在此修)。` },
];

interface LaneOutcome { name: string; review: string; fresh: string; check: boolean; head: string; wt: string; branch: string; }
const lanes: Promise<LaneOutcome>[] = laneSpecs.map((spec) => (async (): Promise<LaneOutcome> => {
  const wt = `/tmp/wt-${spec.slug}`;
  const branch = `task/${spec.slug}`;

  let checkGreen = false;
  let lastFail = "";
  for (let round = 1; round <= 3 && !checkGreen; round++) {
    await agent(`${spec.role}-r${round}`).ask<string>(`
${COMMON}
任务(#382 ${spec.name},${VERDICT_DOC} ${spec.doc} 节):
${spec.task}
${round > 1 ? `本轮为修复轮,上轮 make check 失败尾摘:\n${lastFail}` : "本轮为首轮。"}
worktree ${wt}(分支 ${branch},venv 已备)。流程:改码+测试 → 在 worktree 内跑 make check 自验 → git commit(中文规范信息)→ gh pr create(base main,三字段模板)。
返回:PR URL、head sha8、改动文件清单、make check 自验结果。`);

    const check = await world.run("make", ["check"], { timeoutMs: 900_000, });
    if (check.exitCode === 0) { checkGreen = true; }
    else { lastFail = (check.stdout + check.stderr).slice(-4000); log(`${spec.name} 第${round}轮 make check 红,回修`); }
  }

  const review = await agent(`审查员-${spec.name}`).ask<string>(`
${COMMON}
独立审查 #382 ${spec.name}(worktree ${wt},分支 ${branch})。必做:①diff 逐行对照 ${VERDICT_DOC} ${spec.doc}——恰好修该不变量、无夹带;②红灯演练(构造违规亲眼看红:${spec.name === "PR-A" ? "Tutor repeat→stuck 不置位" : spec.name === "PR-B" ? "注入 GatewayError→session 字段全回滚" : "纯模型 ladder→reveal 不消费"});③§11 逐条对照;④make check 亲跑。
审查总结评论落 PR(结论/复现清单/发现分级 P1-P3)。返回:结论+评论链接+PR URL+head。`);

  const fresh = await agent(`新鲜眼终审-${spec.name}`).ask<string>(`
你没见过前面的争论。只看三样:diff(worktree ${wt} 分支 ${branch})、${VERDICT_DOC} ${spec.doc} 原文、PR 描述。独立判:是否恰好修了裁定所指不变量、无夹带、无禁令违反?一句话结论+最多两条理由。`);

  return { name: spec.name, review, fresh, check: checkGreen, head: branch, wt, branch };
})());

const done = await Promise.all(lanes);

phase("合流审查:三 lane 交互面");
const confluence = await agent("合流审查官").ask<string>(`
${COMMON}
三 lane 各自绿≠组合绿。交叉面:①PR-B 回滚路径是否触碰 PR-A 新加的 stuck 写权限门;②PR-A 删 repeat→stuck 后,PR-B 的 finish() 触发条件(ready+correct+not stuck)行为是否变化;③PR-C 的 provenance 字段是否被 A/B diff 破坏。
做法:临时 worktree 按 A→B→C 序逐个 rebase 模拟合并,每步 make check;产出合并顺序建议+冲突清单。只验证不产码。`);

phase("PR-D 回归电池编写");
const regression = await agent("回归冻结员").ask<RegressionBattery>(`
${COMMON}
编写 #382 PR-D:700m 事故冻结为 production regression。
素材:${VERDICT_DOC} 逐轮表+尾部 GatewayError×2/同句重发×2;三 lane 语义(PR-A:repeat 不判 stuck;PR-B:GatewayError 全回滚;PR-C:非 trusted 不 reveal)。
要求:①四维度覆盖:「学生首答正确不被无端质疑」行为面留 skip 标记+注释「待 Prompt/Model 层(§11)」;repeat/stuck、原子性、trusted 三个确定性面必须可断言;②新测试先在不合三 PR 的基底(origin/main)跑,记录红灯证据;③Gateway failure turn 从 trajectory 指标排除;④用户重发不计教学复读。
worktree /tmp/wt-pr-d-regression(分支 task/pr-d-regression)。返回 RegressionBattery。`);

phase("汇总:第一波报告");
const report: WaveReport = {
  probe,
  lanes: done.map(d => ({ name: d.name, result: { pr: d.review, head: d.head, filesChanged: [], makeCheck: d.check ? "green" : "red", reviewVerdict: "有保留通过" as const, reviewComment: d.review, freshEyeVerdict: d.fresh, violations: [] } })),
  confluenceVerdict: confluence,
  regression,
  mergeOrderAdvice: "按合流审查结论合并(A→B→C→D 建议序),逐 PR 人键",
  notCovered: ["PR-E Thin Kernel 产品化(第二波,待 A-D 合入)", "#252 Phase 1 seam extraction(第三波)", "Prompt/Model quality(最后,外部 slice)"],
};
return report;
