---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: abee4436ed4557f1948eb03bcf75540f_2f4c5ae0e2a311f18c5752540024e231
    ReservedCode1: LKPNGhlBPPjHMbZkMiPLMGd9tbJOlEjN19c+WyRx7+zUX9q+xeoy9OyLMsi5p/xCqUGoJfxW/O9K/7Ta3j7lSPWYZhce6zNtFcb3JSdOnsBKCZfSSyUktT1BDIntacqZ/MOYXBvlNW8mUO9ouEXFC3qJXWVB0poXX50eFeDIMsty/PBRpyshtm2jTQ0=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: abee4436ed4557f1948eb03bcf75540f_2f4c5ae0e2a311f18c5752540024e231
    ReservedCode2: LKPNGhlBPPjHMbZkMiPLMGd9tbJOlEjN19c+WyRx7+zUX9q+xeoy9OyLMsi5p/xCqUGoJfxW/O9K/7Ta3j7lSPWYZhce6zNtFcb3JSdOnsBKCZfSSyUktT1BDIntacqZ/MOYXBvlNW8mUO9ouEXFC3qJXWVB0poXX50eFeDIMsty/PBRpyshtm2jTQ0=
---

# Server酱通知 (serverchan)

通过 Server酱（SCMax / Server酱³）发送消息通知，支持 APP 推送。

## 功能

- 🖼️ 入库通知支持封面图片
- 📥 下载任务添加通知
- 🗑️ 下载任务删除通知
- ✅ 媒体整理完成通知
- 📺 订阅完成通知
- ❌ 系统错误通知
- 💬 用户消息通知

## 配置

| 参数 | 说明 | 获取方式 |
|------|------|----------|
| SendKey | 支持两种格式：SCMax 的 `scx-{UID}-{TOKEN}`、Server酱³ 的 `sctp{UID}t{TOKEN}`，UID 会自动提取 | SCMax: [https://max.ft07.com/](https://max.ft07.com/) ｜ Server酱³: [https://sc3.ft07.com/](https://sc3.ft07.com/) |
| 接口地址（可选） | 留空按 SendKey 前缀自动选择；填写后向 `{接口地址}/send/{SendKey}` 发送，可用于自建或反代域名 | 例：`https://10325.max.ft07.com` |
| 标签 | 消息标签列表 | 多个标签用竖线(\|)分隔 |
| 消息类型 | 选择需要接收的通知类型 | 不选则接收所有 |

### 接口地址自动选择规则

| SendKey 前缀 | 请求地址 |
|--------------|----------|
| `scx-` | `https://{UID}.max.ft07.com/send/{SendKey}`（SCMax） |
| `sctp` | `https://{UID}.push.ft07.com/send/{SendKey}.send`（Server酱³） |
| 任意 + 已填接口地址 | `{接口地址}/send/{SendKey}` |

## 安装方式

1. 打开 MoviePilot 设置 → 插件 → 插件源
2. 添加插件源：`https://github.com/SilentReed/MoviePilot-Plugins`
3. 在插件市场搜索「Server酱通知」并安装

## 版本历史

### v2.2.0

- 新增 SCMax 支持：SendKey 支持 `scx-{UID}-{TOKEN}` 格式，自动切换至 `{UID}.max.ft07.com`
- 新增可选配置「接口地址」，支持自建 / 反代 / 其它兼容 SC3 协议的服务
- SendKey 校验由「必须以 sctp 开头」放宽为「能从 SendKey 提取 UID 或已填接口地址」
- 发送结果判定兼容 SCMax 响应（`code` / `errno` / `message=SUCCESS`）
- 接口返回非 JSON（如 `Invalid sendkey`）时，把原文写入日志，便于定位

### v2.0.0

- 适配 V3 SDK：导入迁移至 `app.sdk` 体系
- HTTP 客户端改用 `AsyncRequestUtils` (HTTPX2)
- 移除旧版兼容层依赖

### v1.8.5

- 版本更新测试

### v1.8.4

- tags 作为 API 原生参数传递
- 多个标签用竖线(|)分隔

### v1.8.3

- 新增标签（tags）配置功能

### v1.8.2

- 入库通知支持封面图片
*（内容由AI生成，仅供参考）*
