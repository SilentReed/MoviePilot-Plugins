# Server酱³通知

MoviePilot 插件，通过 Server酱³ 发送消息通知，支持 APP 推送。

## 功能

- 📥 下载任务添加通知
- 🗑️ 下载任务删除通知
- ✅ 媒体整理完成通知
- 📺 订阅完成通知
- ❌ 系统错误通知
- 💬 用户消息通知

## 安装

1. 打开 MoviePilot 设置 → 插件 → 插件源
2. 添加插件源：`https://github.com/SilentReed/MoviePilot-ServerChan`
3. 在插件市场搜索「Server酱³通知」并安装

## 配置

- **UID**：Server酱³ 用户 ID
- **SendKey**：Server酱³ SendKey
- **消息类型**：选择需要接收的通知类型（不选则接收所有）

## 获取 SendKey

访问 https://sc3.ft07.com/ 注册并获取 SendKey。

## 版本更新

### v1.1.2
- 插件图标路径变更为本地图标

### v1.0.9
- 增加本地图标文件 serverchan.png

### v1.0.8
- 增加插件图标

### v1.0.7
- 修复消息类型过滤逻辑，增加日志输出

### v1.0.6
- 修复 NotificationType 属性错误

### v1.0.5
- 适配 V2 插件规范，使用 get_form 方法
