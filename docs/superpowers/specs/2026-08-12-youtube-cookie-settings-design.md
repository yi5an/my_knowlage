# YouTube Cookie 设置设计

## 目标

让管理员能在 KnowPilot 的“设置”页面粘贴有效的 Netscape/Mozilla 格式
YouTube Cookie 文本，以解除同一代理出口触发的 YouTube “确认你不是机器人”
挑战。Cookie 必须在保存后立即被所有 yt-dlp 下载路径使用，且其正文绝不通过
API、页面、日志、数据库或 Git 返回、保存或输出。

## 范围

本次覆盖以下已有 yt-dlp 调用：

- YouTube 字幕下载；
- ASR 的音频下载；
- 视觉资料的低清视频下载；
- NAS 本地视频下载。

不实现浏览器登录自动化、Cookie 自动续期、PO Token、OAuth，也不在模型管理中
保存 Cookie。

## 方案与取舍

采用“页面粘贴 + 服务器受限文件”的方案。

- 相比路径环境变量：无需管理员 SSH 上传，适合当前平台的浏览器设置场景。
- 相比数据库密文：Cookie 经常轮换、属于完整会话凭据，落库会扩大备份、审计和
  泄露面。
- 相比服务器浏览器：不在服务器保留浏览器 Profile、登录态或密钥环，运维复杂度
  更低。

## 后端设计

### 安全存储

新增 `YouTubeCookieStore` 基础设施服务，存储位置由
`YOUTUBE_COOKIES_FILE` 配置决定。生产 Compose 提供仅挂载给后端的命名持久化卷，
容器内默认路径为 `/app/private/youtube-cookies.txt`。前端、ASR、OCR 等容器均不
挂载该卷。

设置 API 写入时：

1. 检查文本大小上限为 1 MiB；
2. 仅接受以 `# HTTP Cookie File` 或 `# Netscape HTTP Cookie File` 开头的
   Netscape 格式；
3. 至少要求一个 cookie 域为 `youtube.com` 或其子域；
4. 使用原子替换写入路径，文件权限设为 `0600`；
5. 响应和日志只返回状态、更新时间、大小、是否含 `youtube.com`，绝不返回正文。

未配置 Cookie 路径或文件不存在时保持匿名 yt-dlp 行为；若路径配置但写入失败，API
显式报错。删除操作清空受限文件并返回“未配置”。

### API

增加 `/api/v1/settings/youtube-cookies`：

- `GET`：返回 `configured`、`updated_at`、`file_size`、`validation_status`；
- `PUT`：接收 `{ "cookies_text": "..." }`，校验并替换；
- `DELETE`：移除已保存 Cookie；
- `POST /test`：只用当前 Cookie 进行低成本 yt-dlp 元数据验证；响应仅包含成功/失败
  状态与脱敏错误摘要。

Cookie 正文不进入 `workspace_setting`。若需要展示更新时间，则通过文件 stat 实时
读取，不额外落库。

### yt-dlp 接入

抽取共享 `youtube_ydl_options` / `youtube_ydl_command_args` 辅助函数：当受限文件存在
时分别提供 Python yt-dlp 的 `cookiefile` 选项与 CLI 的 `--cookies PATH` 参数。所有
四条路径继续保留代理设置，并使用同一个 Cookie 文件。

## 前端设计

在“设置”页新增“ YouTube 访问 Cookie ”卡片：

- 初始只显示当前配置状态、最后更新时间、文件大小及安全提示；
- 点击“替换 Cookie”后展示多行输入框；输入框不预填，也不持久化到 localStorage；
- “保存并校验”调用 `PUT`，成功后立即清空输入框；
- “测试当前 Cookie”调用测试端点；
- “移除 Cookie”要求二次确认；
- 提示用户从专用账号、无痕窗口导出 `youtube.com` Netscape 格式 Cookie，且在与
  服务器相同代理出口完成验证码。

## 错误处理

- 格式错误：`422 youtube_cookies_invalid_format`；
- 不含 YouTube 域：`422 youtube_cookies_missing_domain`；
- 文件系统写入异常：`500 youtube_cookies_storage_error`；
- 测试请求被 YouTube 拒绝：返回脱敏的 `test_failed`，不返回 Cookie 文本、请求头或
  完整 yt-dlp 命令。

## 测试

- Cookie 格式、YouTube 域、大小与原子存储的单元测试；
- API 测试确保正文不出现在 GET、PUT、错误或日志响应；
- ASR、字幕、视觉资料、NAS 下载的调用测试，断言每条路径都收到同一 `cookiefile` /
  `--cookies` 参数；
- 设置页测试：状态展示、粘贴保存后清空、测试结果、删除确认；
- Compose 测试：受限 Cookie 文件只读挂载、路径由环境变量提供且 `.env.example` 不含
  Cookie 正文。

## 部署与操作

生产 Compose 创建 `backend_private` 命名卷并仅挂载到后端。首次保存时后端创建目录和
Cookie 文件，Cookie 文件权限为 `0600`。首次部署后管理员从页面粘贴 Cookie；不再需要
将 Cookie 通过 SSH 或 Git 传输。
