# 返回格式与错误码

[在线调试 Swagger](/api/docs) · [返回 API 文档](/api/docs/public-api.md) · [查看原始 Markdown](/api/docs/guides/response-conventions/raw.md)

## 1. 成功响应

多数接口直接返回资源对象。部分统一封装接口返回：

```json
{
  "request_id": "req_xxx",
  "data": {
    "task_id": "task_xxx",
    "status": "queued"
  }
}
```

`request_id` 用于日志查询。异步接口通常同时返回业务资源 ID、`task_id` 和查询地址。

## 2. 失败响应

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "当前身份没有调用该接口的权限。",
    "details": {
      "required_action": "请使用具有对应权限的账号或接口密钥后重试。"
    }
  },
  "request_id": "req_xxx"
}
```

前端优先展示 `message`。`details` 用于补充缺失字段、冲突状态或建议操作，
不要直接展示服务端堆栈或内部路径。

## 3. 常见状态码

| 状态码 | 含义 | 建议处理 |
| --- | --- | --- |
| `400` | 请求格式或业务参数错误 | 修正请求后再提交。 |
| `401` | 未登录或凭证无效 | 重新登录或更换有效凭证。 |
| `403` | 当前身份没有权限 | 不要自动重试，先检查权限。 |
| `404` | 资源不存在或不可见 | 检查资源 ID 和当前身份。 |
| `409` | 状态冲突或并发更新冲突 | 重新读取资源后再决定下一步。 |
| `422` | 输入缺失或校验失败 | 根据 `details` 补充或修正输入。 |
| `429` | 请求过多或额度不足 | 按服务端提示延迟重试。 |
| `500` | 服务端异常 | 保留 `request_id`，按幂等规则重试。 |
| `503` | 依赖服务暂不可用 | 稍后重试，不要把失败结果标记为成功。 |

## 4. 常见错误码

| 错误码 | 含义 |
| --- | --- |
| `UNAUTHORIZED` | 未建立有效身份。 |
| `FORBIDDEN` | 当前身份没有权限。 |
| `NOT_FOUND` | 资源不存在或当前身份不可见。 |
| `VALIDATION_ERROR` | 请求结构不符合接口定义。 |
| `SKILL_SESSION_CONFLICT` | 当前会话存在冲突的技能状态。 |
| `MICRO_LESSON_PREFLIGHT_REQUIRED` | 微课材料不完整，尚未创建任务。 |
| `IDEMPOTENCY_CONFLICT` | 同一防重复键对应了不同请求。 |
| `TASK_NOT_CANCELLABLE` | 当前任务状态不允许取消。 |

## 5. 重试原则

1. `401`、`403`、`404` 和普通 `422` 不自动重试。
2. `409` 先读取最新状态，再决定是否提交。
3. `429`、`500`、`503` 仅在接口具备幂等保护时重试。
4. 创建类接口优先传 `Idempotency-Key` 或请求体中的 `idempotency_key`。
5. 文件上传、任务创建和结果读取使用各自的资源 ID，不根据提示文字推断状态。
