# JD 截图与链接输入安全契约

## 范围

默认分支已交付 `app.ports.jd_input.JdInputPort` 的截图 OCR（#136，百度智能云）与受控链接抓取（#137）Adapter、
公开预览 API（`POST /job-postings/image`、`POST /job-postings/fetch`）。两者都只返回正文预览，不直接创建岗位；
用户确认后经既有 `POST /job-postings` 文本路径进入快照。

## 图片边界

- 只接受 `image/png` 和 `image/jpeg`，且 MIME 必须与 PNG/JPEG 文件签名一致；扩展名不作为格式证据。
- 单张图片最大 `10 MiB`，在解码和 OCR 前检查；超限返回 `image_too_large`。
- 空内容、未知格式或 MIME/签名不一致返回 `unsupported_image`；无法解码返回 `decode_failed`。
- OCR Adapter 失败返回 `ocr_failed`，不得猜测或生成 JD 正文。
- OCR 结果为空返回 `empty_content`，超过 `100,000` 字符返回 `content_too_large`。

图片解码器仍需在隔离资源限制内运行。像素尺寸、解压膨胀和解码器漏洞防护属于 M2 Adapter 的实现审查项，不能用当前字节大小检查替代。
百度智能云 OCR（`accurate_basic`）对 base64 图片约 `4 MB` 上限，低于上传端口 `10 MiB`；超过该上限的图片会在百度侧失败并返回 `ocr_failed`，部署时应优先对截图做降采样或压缩后再上传。

## URL 与 SSRF 边界

抓取 Adapter 必须遵循以下顺序，任一步失败都不得返回猜测内容：

1. 仅允许 `http`/`https`，拒绝 URL 凭据、fragment、空主机、无效端口和超过 2,048 字符的 URL。
2. 规范化 IDNA 主机名，拒绝 `localhost`、本地域名后缀和非全局 IP literal。
3. 使用受控 DNS resolver 解析全部 A/AAAA 结果；只要任一结果不是公网单播地址（包括组播地址）就返回 `unsafe_url`。
4. 将实际连接固定到已经校验的地址，同时保持正确的 Host/SNI；不得在校验后再次进行未受控解析，以避免 DNS rebinding 和 TOCTOU。
5. 不自动跟随重定向。每次跳转都重新执行 URL、DNS 和 IP 校验，最多 3 次；超限返回 `too_many_redirects`。
6. 连接超时 5 秒、读取超时 10 秒；超时返回 `fetch_timeout`，其他网络失败返回 `fetch_failed`。
7. 流式读取正文，压缩前后均执行资源限制，最多 2 MiB；超限立即中止并返回 `response_too_large`。
8. 只把成功获取且明确解析出的文本交给 `JdInputResult`；最终 URL 保存在 `source_url`，网页内容始终作为不可信数据。

代理环境变量、Cookie、认证头、客户端证书和用户浏览器登录态不得转发给目标站点。Adapter 应禁用非 HTTP 协议升级，记录稳定错误码、耗时与目标域名，但不得记录完整 JD、查询中的敏感值或响应正文。

## 稳定失败分类

| 错误码 | 含义 |
|---|---|
| `unsupported_image` | 图片格式、签名或内容不受支持 |
| `image_too_large` | 上传图片超过 10 MiB |
| `decode_failed` | 图片无法解码或超过像素/尺寸限制 |
| `invalid_url` | URL 语法或结构不合法 |
| `unsafe_url` | 主机或解析地址不满足公网边界 |
| `too_many_redirects` | 重定向超过 3 次 |
| `response_too_large` | 抓取响应超过 2 MiB |
| `fetch_timeout` | 连接或读取超时 |
| `fetch_failed` | DNS 或其他网络抓取失败 |
| `ocr_failed` | OCR Provider 明确失败 |
| `empty_content` | OCR/抓取未产生可用文本 |
| `content_too_large` | 提取文本超过岗位正文上限 |
| `invalid_input_kind` | Adapter 返回了契约以外的输入类型 |

## M2 实现审查与测试要求

- Fake/contract tests：OCR 与抓取 Adapter 均满足 `JdInputPort`，错误码保持稳定。
- SSRF tests：IPv4/IPv6 私网、loopback、link-local、组播、保留地址、混合 DNS 结果和 DNS rebinding。
- Redirect tests：每一跳重新解析与校验，协议切换、私网跳转和第 4 次跳转均失败。
- Resource tests：声明长度和流式实际长度分别超限，压缩膨胀、连接超时和读取超时可中止。
- API tests：认证、上传 MIME/大小、URL DTO、稳定错误响应以及成功结果进入既有 JobPosting 创建路径。

这些是 M2 Adapter 与公开调用路径的强制验收项，不表示 OCR 或链接抓取当前已经可用。
