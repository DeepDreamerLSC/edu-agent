# corpus checks × 真模型轮次报告(#216)

- 生成:2026-09-14T09:21:46.686407+00:00
- 工件:edu_agent/evals/artifacts/gepa-prereqs-trial
- judger_sha256:440395a900bfdd09828c75ff8ffe211c8b80b0c9a5a6512eb90a2e882e6ed446
- 对照基线:无(首轮即基线;下轮用 --diff-from 指向本轮 collect 下最新 run 目录)

| case_id | status | final_state | checks | 判定(跨轮) | judge |
|---|---|---|---|---|---|
| gepa-trial-b2_circle_area_support_boundary | ok | completed | 无声明 | - | total=11 pass 追问=1 |
| gepa-trial-b2_circle_area_support_boundary_hard_pressure | ok | needs_review | 无声明 | - | total=3 fail 追问=0 |
| gepa-trial-b2_fraction_multiplication_complete_reasoning | ok | completed | 无声明 | - | total=6 fail 追问=0 |
| gepa-trial-b2_rope_unit_app_misconception_repair | ok | completed | 无声明 | - | total=12 pass 追问=2 |
| gepa-trial-pilot_stability_fraction_addition | ok | completed | 全绿 | - | total=10 pass 追问=2 |
| gepa-trial-pilot_stability_rectangle_perimeter | ok | needs_review | finish_status:final_state 期望 completed,实际 needs_review | - | total=5 fail 追问=1 |

## 三口径 × 四指标(#238 件 B,GEPA 前置)

口径注记:
- primary-only = ok case 中 tutor 会话与 judge 会话均未走 fallback 的子集
  (tutor 备选 mlx_27b / judge 备选 deepseek;case 级 = 任一调用 fallback 即出局,
  GEPA 归因要的干净集——优化对象是 system score 还是 primary-only 由此可判)
- with-fallback = 全部 ok case(system 实产口径);fallback-rate = 调用级按 role 分列
- turns-to-confirm = completed 帧学生轮数均值(一轮 = 一学生消息 + 一导师回应,首问不计)
- false-confirm(代理)= completed ∧ 期望答案含 ASCII 数字 ∧ 期望数字集未全现于
  学生消息;定性答案不进分母,中文数字不在判据内(已知盲区)
- stuck = guard_events 出现 reveal 分支(窄词表「不会」族)占比;
  needs-review = final_state=needs_review 占比;judge 均值 = total/12 口径内均值

| 口径 | n | completed | turns-to-confirm | false-confirm | stuck | needs-review | judge 均值 |
|---|---|---|---|---|---|---|---|
| primary-only | 6 | 4 | 2.2 | 1/1 (100.0%) | 16.7% | 33.3% | 7.8 |
| with-fallback | 6 | 4 | 2.2 | 1/1 (100.0%) | 16.7% | 33.3% | 7.8 |

调用级 fallback:

| role | calls | fallbacks | rate |
|---|---|---|---|
| judge | 6 | 0 | 0.0% |
| tutor | 30 | 0 | 0.0% |
