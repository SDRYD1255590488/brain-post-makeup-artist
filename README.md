# BRAIN Post Makeup Artist

中文 | [English](#english)

## 中文介绍

`brain-post-makeup-artist` 是一个用于 WorldQuant BRAIN / Zendesk Community 论坛的排版、审计、发布和回读 Skill。

它把 Markdown 或已有 HTML 整理成论坛兼容的长帖，提供可复用的提示框、KPI 面板、表格、时间线、图片、公式、折叠区和页内导航组件。所有组件都基于论坛实际回读结果，而不是仅凭浏览器预览推测。

### 主要能力

- Markdown → 论坛兼容 HTML
- 严格检查不支持的标签、CSS、外部图片、普通 `id` 和敏感信息
- 本地图片注册为 `/hc/user_images/...`
- API 创建、更新和回读帖子
- API 与渲染 DOM 的结构计数核对
- 桌面、平板和手机预览
- AI_ONLY 测试帖的单帖探针与端到端验收
- 凭据从本地配置导入，`.env` 权限固定为 `0600`

### 认证与发布方式

稳定的论坛发布流程是：

```text
BRAIN API 登录
  → Playwright 建立 Support SSO 会话
  → 在同一浏览器上下文中获取 Cookie / CSRF
  → 使用同源论坛 API 创建或更新正文
  → API + 页面渲染回读
```

浏览器只负责 Support SSO、风控会话和必要的 User Image 注册；正文写入仍然是 API。发布命令只允许一次 consequential POST/PUT，结果不明确时会停止并写入未知状态标记，禁止自动重试。

纯 HTTP Support SSO 保留为诊断路径，不是默认发布路径；普通客户端可能在 SSO 阶段收到 403。

### 快速开始

```bash
uv sync
uv run python scripts/configure_env.py
uv run python scripts/forum_skill.py doctor --auth
```

准备好草稿后：

```bash
uv run python scripts/forum_skill.py compose \
  --input draft.md \
  --title "Exact title" \
  --mode polish \
  --theme emerald \
  --output-dir .forum-runs/my-post

uv run python scripts/forum_skill.py audit \
  --html .forum-runs/my-post/post.html --strict

uv run python scripts/forum_skill.py preview \
  --html .forum-runs/my-post/post.html \
  --output-dir .forum-runs/my-post/preview
```

只有在用户明确确认标题、主题和最终正文后，才运行 `publish` 或单进程 `acceptance`。详细约束见 [SKILL.md](SKILL.md)。

### 安全边界

- `.env`、Cookie、CSRF、JWT、Token、签名上传 URL 和本地运行证据不会提交。
- 不会把账号密码写进帖子、README 或日志。
- 不使用 `<script>`、`<style>`、外部图片、MathML 或未经验证的 CSS Grid。
- 本项目不保证所有论坛标签永久兼容；平台升级后应重新执行探针和回读审计。

### 依赖与版本

`pyproject.toml` 保存可接受的直接依赖范围，`uv.lock` 保存本项目当前验证过的精确解析版本。建议使用 `uv sync`，不要手动混装依赖。

| 依赖 | 声明范围 | 当前锁定版本 | 用途 |
| --- | --- | --- | --- |
| Python | `>=3.11` | 本机验证 `3.12.13` | 运行 Skill 脚本 |
| beautifulsoup4 | `>=4.12` | `4.15.0` | HTML 解析与结构统计 |
| mistune | `>=3.0` | `3.3.4` | Markdown 转换 |
| playwright | `>=1.50` | `1.62.0` | Support SSO、User Image 注册、页面回读 |
| requests | `>=2.32` | `2.34.2` | BRAIN API 认证与 HTTP 辅助请求 |

也提供 pip 兼容入口，便于不使用 UV 的使用者：

```bash
python -m pip install -r requirements.txt
```

`requirements.txt` 会引用精确版本的 `requirements.lock.txt`。两者由 `uv.lock` 导出；`uv.lock` 仍是唯一带工件哈希的权威锁文件，因此维护者更新依赖时应先执行 `uv lock`。

Playwright Python 包和浏览器二进制是两件事。若希望使用匹配版本的 bundled Chromium，可执行：

```bash
uv run playwright install chromium
```

如果该浏览器二进制尚未安装，默认 `BRAIN_FORUM_CHROME_CHANNEL=auto` 会在启动前选择已安装的系统 Chrome；不会先启动失败再自动重试。

## English

`brain-post-makeup-artist` is a formatting, auditing, publishing, and readback Skill for WorldQuant BRAIN / Zendesk Community forums.

It turns Markdown or existing HTML into forum-compatible long-form posts and provides reusable callouts, KPI panels, tables, timelines, figures, formulas, foldouts, and in-page navigation. Components are based on saved platform readbacks, not on browser previews alone.

### Features

- Markdown-to-forum HTML composition
- Strict validation of unsupported tags/CSS, external images, ordinary `id` targets, and sensitive text
- Local image registration as `/hc/user_images/...`
- API-based post creation, updates, and readback
- Source-versus-rendered structure checks
- Desktop, tablet, and mobile previews
- AI_ONLY probes and one-session end-to-end acceptance runs
- Secure local credential import with `.env` mode `0600`

### Authentication and publishing architecture

The proven publishing path is:

```text
BRAIN API authentication
  → Playwright establishes the Support SSO session
  → Cookies / CSRF stay in one authenticated browser context
  → Same-origin forum APIs create or update the post
  → API and rendered-page readback
```

The browser is used for Support SSO, anti-bot session establishment, and required User Image registration. Post content is still written through APIs. Each live create/update permits only one consequential request; ambiguous results stop the workflow and block retries.

The pure-HTTP Support SSO path is retained for diagnostics only. Ordinary HTTP clients may receive a 403 before topic lookup.

### Quick start

```bash
uv sync
uv run python scripts/configure_env.py
uv run python scripts/forum_skill.py doctor --auth
```

Compose, audit, and preview a draft with the commands shown in the Chinese section above. Run `publish` or the single-session `acceptance` command only after explicit confirmation of the exact title, topic, and final body.

### Safety

- Credentials, cookies, CSRF tokens, JWTs, upload signatures, and local run evidence are ignored and never committed.
- Account credentials are never written to posts, README files, or logs.
- The Skill avoids scripts, `<style>`, external images, MathML, and unverified CSS Grid.
- Forum compatibility is empirical and can change after platform updates; rerun probes and readback audits after major changes.

### Dependencies and versions

`pyproject.toml` declares acceptable direct-dependency ranges, while `uv.lock` records the exact versions resolved and validated for this repository. Use `uv sync` instead of mixing manually installed packages.

| Dependency | Declared range | Locked version | Purpose |
| --- | --- | --- | --- |
| Python | `>=3.11` | Verified locally with `3.12.13` | Run the Skill scripts |
| beautifulsoup4 | `>=4.12` | `4.15.0` | Parse HTML and count structures |
| mistune | `>=3.0` | `3.3.4` | Convert Markdown |
| playwright | `>=1.50` | `1.62.0` | Support SSO, User Image registration, and page readback |
| requests | `>=2.32` | `2.34.2` | BRAIN API authentication and HTTP helpers |

A pip-compatible installation entry point is also included for users who do not use UV:

```bash
python -m pip install -r requirements.txt
```

`requirements.txt` includes the exact-version `requirements.lock.txt`. Both are exported from `uv.lock`; `uv.lock` remains the only authoritative lockfile with artifact hashes, so maintainers should run `uv lock` first when changing dependencies.

The Playwright Python package and its browser binary are separate dependencies. To install the version-matched bundled Chromium, run:

```bash
uv run playwright install chromium
```

When the bundled browser is not installed, the default `BRAIN_FORUM_CHROME_CHANNEL=auto` selects an installed system Chrome before launch; it does not launch once, fail, and then retry automatically.

## Repository layout

```text
SKILL.md                 Skill instructions and safety contracts
assets/                  Reusable components, themes, and sample content
references/              Compatibility, platform, and acceptance guidance
scripts/                 Compose, audit, preview, platform, and config tools
tests/                   Offline regression tests
evals/                   Trigger and behavior evaluation cases
```

## License

MIT. See [LICENSE](LICENSE).
