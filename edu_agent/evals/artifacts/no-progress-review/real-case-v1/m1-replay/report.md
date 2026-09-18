# corpus checks × 真模型轮次报告(#216)

- 生成:2026-09-18T06:32:03.231758+00:00
- 工件:out/np-real
- judger_sha256:de5a9cd9f57bc9dd97800d13d07798d9652a30593720d6496bad6bd2e06e13b5
- 对照基线:无(首轮即基线;下轮用 --diff-from 指向本轮 collect 下最新 run 目录)

| case_id | status | final_state | checks | 判定(跨轮) | judge |
|---|---|---|---|---|---|
| small_lecturer_no_progress_real_v1_no-progress-real-6a61aa32-replay | ok | needs_review | 全绿 | - | total=3 fail 追问=0 |

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
| primary-only | 1 | 0 | - | 0/0 (-) | 0.0% | 100.0% | 3.0 |
| with-fallback | 1 | 0 | - | 0/0 (-) | 0.0% | 100.0% | 3.0 |

调用级 fallback:

| role | calls | fallbacks | rate |
|---|---|---|---|
| judge | 1 | 0 | 0.0% |
| tutor | 11 | 0 | 0.0% |
