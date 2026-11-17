---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: abee4436ed4557f1948eb03bcf75540f_34c7318ce2b011f18c5752540024e231
    ReservedCode1: KR4wvkLjB9zML9iOrKlTvRd4mSpvAtMwLcpPH1iEd5wpPLca+6nl2/EDMK15cdq6e06VIfcnEFbOFbXhLd4JuFZP6dMaTJNqLnk+0JmEfUzIGy0M8qpc3CaQLMIuHAPb4/5mkTdZpITf4qcEgltwcsEmppa54ql4cBNtH6Fy9ry9fWdxPn9qm8wd7bM=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: abee4436ed4557f1948eb03bcf75540f_34c7318ce2b011f18c5752540024e231
    ReservedCode2: KR4wvkLjB9zML9iOrKlTvRd4mSpvAtMwLcpPH1iEd5wpPLca+6nl2/EDMK15cdq6e06VIfcnEFbOFbXhLd4JuFZP6dMaTJNqLnk+0JmEfUzIGy0M8qpc3CaQLMIuHAPb4/5mkTdZpITf4qcEgltwcsEmppa54ql4cBNtH6Fy9ry9fWdxPn9qm8wd7bM=
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

## 正文排版优化

上游插件推送的多行文本（如「站点管理」的 `1. 名称 | 状态：启用 | Cookie：已配置 | 渲染：否 | 域名：xxx`）在微信端常被合并成一大段、且标题重复出现。开启「正文排版优化」（默认开启）后，插件会：

- 去掉与标题重复的首行
- 把条目行拆成「**序号 + 名称**」加粗标题，与「状态 · Cookie · 渲染 · 域名」要点行两行展示
- 为非空行补 Markdown 硬换行（行尾双空格），避免换行被吞
- 检测到 Markdown 表格或代码块时保持原样，不破坏既有结构

关闭该开关则退回旧行为（`标题 + 空行 + 原始正文`）。

## 配置

| 参数 | 说明 | 获取方式 |
|------|------|----------|
| SendKey | 支持两种格式：SCMax 的 `scx-{UID}-{TOKEN}`（需同时填接口地址）、Server酱³ 的 `sctp{UID}t{TOKEN}` | SCMax: [https://max.ft07.com/](https://max.ft07.com/) ｜ Server酱³: [https://sc3.ft07.com/](https://sc3.ft07.com/) |
| 接口地址 | **使用 SCMax（`scx-` 开头）时必填**，填写账户专属推送地址；Server酱³（`sctp` 开头）可留空自动判断。插件向 `{接口地址}/send/{SendKey}` 发送 | SCMax 控制台首页可见，例：`https://10325.max.ft07.com` |
| 标签 | 消息标签列表 | 多个标签用竖线(\|)分隔 |
| 消息类型 | 选择需要接收的通知类型 | 不选则接收所有 |
| 正文排版优化 | 默认开启，整理换行与条目格式 | 建议保持开启 |

### 接口地址自动选择规则

| SendKey 前缀 | 接口地址 | 请求地址 |
|--------------|----------|----------|
| `scx-` | 必填 | `{接口地址}/send/{SendKey}`（SCMax） |
| `sctp` | 可留空 | 留空时 `https://{UID}.push.ft07.com/send/{SendKey}.send`（Server酱³） |
| 任意 | 已填 | `{接口地址}/send/{SendKey}` |

## 安装方式

1. 打开 MoviePilot 设置 → 插件 → 插件源
2. 添加插件源：`https://github.com/SilentReed/MoviePilot-Plugins`
3. 在插件市场搜索「Server酱通知」并安装

## 版本历史

### v2.3.0

- 新增「正文排版优化」开关（默认开启）
- 去掉正文中与标题重复的首行
- `1. 名称 | k：v | k：v` 条目拆成加粗标题行与要点行
- 非空行补 Markdown 硬换行，修复微信端多行被挤成一段的问题
- Markdown 表格 / 代码块场景保持原样

### v2.2.1

- 使用 SCMax（`scx-` 开头 SendKey）时「接口地址」改为必填，需填账户专属推送地址（如 `https://{UID}.max.ft07.com`）
- Server酱³ 仍可留空，按 UID 自动走 `push.ft07.com`

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
*（内容由AI生成，仅供参考）*
