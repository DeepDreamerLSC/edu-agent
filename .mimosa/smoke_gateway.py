"""M0 冒烟(01 §10):云 API(DeepSeek)+ 本地服务(mlx-lm 8301)invoke/stream。

凭据只从环境变量读;脚本放 .mimosa/(gitignore 外的未跟踪目录),不入库。
"""

import json
from pathlib import Path

from edu_agent.gateway import Gateway, ModelRequest, load_registry

facts = Path("/tmp/edu-smoke-facts")
registry = load_registry("configs/models.yaml")
gateway = Gateway(registry, facts)

req = ModelRequest(
    role="tutor",
    messages=[{"role": "user", "content": "用一句话说明什么是质数"}],
    session_id="smoke-local",
    max_tokens=64,
)

# 1) 本地 mlx-lm: invoke
resp = gateway.invoke(req)
print("LOCAL invoke ok:", resp.finish_reason, resp.input_tokens, "->", resp.output_tokens,
      "|", resp.text[:40].replace("\n", " "))

# 2) 本地 mlx-lm: stream(首 token 计时见事实记录 ttft)
text = ""
done = None
for event in gateway.stream(req):
    if event.kind == "token":
        text += event.text
    else:
        done = event.response
print("LOCAL stream ok:", done.finish_reason, done.output_tokens, "|", text[:40].replace("\n", " "))

# 3) 云 API DeepSeek: judge 角色 invoke + stream(凭据来自环境变量 DEEPSEEK_API_KEY)
judge_req = ModelRequest(
    role="judge",
    messages=[{"role": "user", "content": "判断:3 是质数吗?只回答是或否"}],
    session_id="smoke-cloud",
    max_tokens=32,
)
resp = gateway.invoke(judge_req)
print("CLOUD invoke ok:", resp.finish_reason, resp.model, resp.input_tokens, "->", resp.output_tokens,
      "|", resp.text[:40].replace("\n", " "))
text = ""
done = None
for event in gateway.stream(judge_req):
    if event.kind == "token":
        text += event.text
    else:
        done = event.response
print("CLOUD stream ok:", done.finish_reason, done.model, "|", text[:40].replace("\n", " "))
gateway.close()

for line in sorted(facts.glob("*.jsonl"))[0].read_text(encoding="utf-8").strip().splitlines():
    payload = json.loads(line)
    print("FACT:", payload["edu.role"], payload["edu.outcome"], "attempt", payload["edu.attempt"],
          "ttft", payload["gen_ai.server.time_to_first_token"], "ms total", payload["edu.total_ms"],
          "tok_in/out", payload["gen_ai.usage.input_tokens"], payload["gen_ai.usage.output_tokens"])
