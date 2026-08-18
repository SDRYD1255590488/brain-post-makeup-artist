# BRAIN Post Makeup Artist

中文 | [English](#english)

把想法、笔记、Markdown、HTML 或研究材料，整理成结构清晰、样式稳定并可安全发布到 WorldQuant BRAIN Support 论坛的帖子。

`brain-post-makeup-artist` 是一个面向 Agent 的可执行 Skill。它不只是给正文换颜色：Agent 会先理解读者和目标，再组织摘要、章节和阅读路径，选用经过平台验证的组件，完成兼容性审计，并在用户确认后通过受保护的流程发布或更新。

## 它解决什么问题

论坛富文本编辑器会重写粘贴内容，很多在本地看起来正常的 HTML、CSS、锚点和图片地址发布后会被移除或降级。本项目把已经验证过的排版知识和发布流程固化为可复用工具：

- 从一句需求、散乱材料或已有草稿生成完整帖子结构
- 提供提示框、表格、指标面板、时间线、折叠详情、公式和图片组件
- 自动生成目录与命名锚点，正文从 `h2` 开始，避免平台标题重复
- 在发布前检查不兼容标签、样式、外链图片、占位符和敏感信息
- 纯文本或永久图片正文优先使用纯 HTTP API，不启动浏览器
- 本地图片通过 Zendesk User Images 注册为永久 `/hc/user_images/...` 地址
- 创建、更新和回读都有精确目标确认、重复保护和未知结果保护

样式能力来自真实 BRAIN Support 回读，不是假设所有浏览器 HTML 都能被平台保留。

## 适用范围

本项目专门支持 **WorldQuant BRAIN Support 论坛**。论坛底层使用 Zendesk Community，但认证、SSO 和图片会话与 WorldQuant 环境绑定，因此它不是无需改造即可用于任意 Zendesk 租户的通用发布器。

它可以被任何能够完成以下操作的 Agent 使用：

- 读取 `SKILL.md`
- 运行本地命令
- 读写工作文件
- 在真实发布前向用户确认标题、版块和操作

不同 Agent 产品的 Skill 安装方式可能不同；仓库内的执行接口和安全约束保持一致。

## 五分钟开始

### 1. 安装

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/SDRYD1255590488/brain-post-makeup-artist.git
cd brain-post-makeup-artist
uv sync
```

如果只发布无新本地图片的帖子，到这里不需要安装浏览器。

### 2. 配置账号

如果当前机器已有 `brain-mcp-v2` 配置：

```bash
uv run python scripts/configure_env.py
```

脚本只把凭据写入本地、被 Git 忽略的 `.env`，权限为 `0600`，不会输出密码。

其他环境请复制 `.env.example` 为 `.env`，填写自己的 BRAIN 账号：

```dotenv
BRAIN_EMAIL=you@example.com
BRAIN_PASSWORD=your-password
```

不要把 Cookie、CSRF Token、JWT 或浏览器请求复制到配置文件。

### 3. 检查环境

文本发布只需检查 BRAIN 认证：

```bash
uv run python scripts/forum_skill.py doctor --auth
```

本地图片注册或浏览器型更新才需要安装并检查浏览器：

```bash
uv run python scripts/install_browser.py
uv run python scripts/forum_skill.py doctor --auth --browser
```

### 4. 交给 Agent

把本仓库作为 Skill 提供给 Agent，然后直接描述目标。例如：

```text
使用 $brain-post-makeup-artist 写一篇面向 BRAIN 新用户的论坛帖子。
主题是 XXX，材料如下：……
先整理结构并生成本地预览，未经我确认不要发布。
```

已有草稿时：

```text
使用 $brain-post-makeup-artist 保留原意，把这份 Markdown 排版成专业的 BRAIN 论坛帖子。
默认使用 polish 模式，发布前告诉我准确标题、目标版块和审计结果。
```

Agent 的完整配置与执行说明见 [Agent 操作手册](references/agent-guide.md)。

## 发布路径怎么选

| 任务 | 推荐路径 | 浏览器 |
|---|---|---|
| 只生成草稿、审计、HTML 预览 | `compose` → `audit` → `preview` | 不需要 |
| 创建纯文本/HTML 帖子，没有新本地图片 | `pure-api-publish` | 不需要 |
| 创建帖子并注册本地图片 | `publish-source` | 需要 |
| 更新已有帖子 | 两阶段 `update` | 需要 |
| 给已有帖子新增本地图片 | `upload` → 重新 `compose` → 两阶段 `update` | 需要 |

本地 HTML 预览不会启动 Playwright。浏览器只用于当前平台确实要求浏览器会话的图片注册和已有帖子更新。

## 手动生成草稿

```bash
uv run python scripts/forum_skill.py compose \
  --input draft.md \
  --title "准确的帖子标题" \
  --mode polish \
  --theme emerald \
  --output-dir .forum-runs/my-post

uv run python scripts/forum_skill.py audit \
  --html .forum-runs/my-post/post.html \
  --title "准确的帖子标题" \
  --strict

uv run python scripts/forum_skill.py preview \
  --html .forum-runs/my-post/post.html \
  --title "准确的帖子标题" \
  --output-dir .forum-runs/my-post/preview
```

`preview` 生成可直接打开的 `rendered.html`。真实发布仍必须由用户确认。

## 安全模型

- 每次真实创建或更新都需要 `--execute` 和准确的确认值。
- 发布前重新解析目标 Topic；更新前同时绑定 Post ID、URL 和当前正文 SHA-256。
- 创建成功标记防止同一运行目录重复创建。
- 如果 POST/PUT 已派发但结果不确定，写入 `operation_unknown.json` 并停止；不能盲目重试。
- 只允许永久 `/hc/user_images/...` 图片地址进入最终正文。
- 保存的响应和元数据会脱敏；不保存 Cookie、CSRF、JWT、密码或签名上传地址。
- `.env`、`.forum-runs/`、浏览器缓存和本地生成资产均被 Git 忽略。

## 依赖与可复现性

- Python：3.11+
- 依赖声明：[pyproject.toml](pyproject.toml)
- 标准锁文件：[uv.lock](uv.lock)
- pip 入口：[requirements.txt](requirements.txt)
- pip 解析版本：[requirements.lock.txt](requirements.lock.txt)
- Playwright 浏览器：仅图片或浏览器型更新需要，由 `scripts/install_browser.py` 安装到仓库隔离缓存

`uv.lock` 是 Python 依赖的权威锁文件。不要提交 `.venv/` 或 `.playwright-browsers/`。

当前锁定的核心包：

| 包 | 版本 | 用途 |
|---|---:|---|
| `beautifulsoup4` | 4.15.0 | HTML 规范化、组件处理与回读分析 |
| `mistune` | 3.3.4 | Markdown 转换 |
| `requests` | 2.34.2 | BRAIN 认证与纯 HTTP 发布 |
| `playwright` | 1.62.0 | 图片编辑器会话与浏览器型更新 |

## 文档导航

- [SKILL.md](SKILL.md)：Agent 触发条件、核心流程和安全不变量
- [Agent 操作手册](references/agent-guide.md)：配置、命令选择、输入输出和排障
- [平台架构](references/platform-architecture.md)：BRAIN、Support SSO、Zendesk、CSRF 与 User Images 的关系
- [平台操作流程](references/platform-workflow.md)：认证、创建、更新、图片和回读检查表
- [HTML 兼容性](references/compatibility.md)：稳定组件与平台边界
- [能力清单](references/capabilities.json)：机器可读的标签、属性和样式支持范围
- [验收标准](references/acceptance.md)：发布前质量门槛

## English

Turn ideas, notes, Markdown, HTML, or research material into structured, platform-compatible posts that can be safely published to the WorldQuant BRAIN Support forum.

`brain-post-makeup-artist` is an executable Skill for coding agents. It does more than apply colours: the agent identifies the audience and goal, shapes the summary and reading flow, selects platform-tested components, audits compatibility, and uses guarded create or update workflows only after user confirmation.

## What it solves

Rich-text editors rewrite pasted content. HTML, CSS, anchors, and image URLs that look correct locally may be stripped or degraded after publication. This project packages verified BRAIN Support behaviour into a repeatable workflow:

- Build a complete post from a short request, rough notes, or an existing draft
- Use callouts, tables, KPI panels, timelines, foldouts, formulas, and figures
- Generate navigation with named anchors and keep the platform title outside the body
- Detect unsupported markup, external images, placeholders, and sensitive information
- Publish text or permanent-image HTML through a browserless HTTP path
- Register local images as permanent Zendesk User Images when needed
- Guard creates and updates with exact confirmation, duplicate prevention, and unknown-outcome markers

The compatibility model is based on real BRAIN Support readback evidence, not generic browser HTML support.

## Scope

This repository targets the **WorldQuant BRAIN Support forum**. The forum runs on Zendesk Community, but its authentication, SSO, and image-session behaviour are WorldQuant-specific. The project is not a drop-in publisher for arbitrary Zendesk tenants.

It works with agents that can read `SKILL.md`, execute local commands, read and write work files, and request confirmation before a live write. Installation or discovery differs by agent product; the repository interface remains the same.

## Five-minute setup

### 1. Install

Python 3.11+ and [uv](https://docs.astral.sh/uv/) are required.

```bash
git clone https://github.com/SDRYD1255590488/brain-post-makeup-artist.git
cd brain-post-makeup-artist
uv sync
```

A browser is not required for posts that do not register new local images.

### 2. Configure credentials

If the machine already has a local `brain-mcp-v2` configuration:

```bash
uv run python scripts/configure_env.py
```

The script writes credentials only to the ignored local `.env`, enforces mode `0600`, and never prints the password.

Otherwise copy `.env.example` to `.env` and add the user's own BRAIN credentials. Never paste cookies, CSRF tokens, JWTs, or copied browser requests into configuration.

### 3. Check readiness

For text publishing:

```bash
uv run python scripts/forum_skill.py doctor --auth
```

Install and check the browser only for local images or browser-backed updates:

```bash
uv run python scripts/install_browser.py
uv run python scripts/forum_skill.py doctor --auth --browser
```

### 4. Ask an agent

```text
Use $brain-post-makeup-artist to write a beginner-friendly BRAIN forum post about XXX.
Here is my source material: …
Prepare and preview it locally, but do not publish without my confirmation.
```

For an existing draft:

```text
Use $brain-post-makeup-artist to preserve the meaning and turn this Markdown into a professional BRAIN forum post.
Use polish mode and show me the exact title, topic, and audit result before publishing.
```

See the [Agent operator guide](references/agent-guide.md) for the complete configuration, command, artifact, and troubleshooting contract.

## Choose the right path

| Task | Recommended path | Browser |
|---|---|---|
| Draft, audit, and local HTML preview | `compose` → `audit` → `preview` | No |
| Create text/HTML without a new local image | `pure-api-publish` | No |
| Create a post and register local images | `publish-source` | Yes |
| Update an existing post | two-pass `update` | Yes |
| Add a local image to an existing post | `upload` → re-compose → two-pass `update` | Yes |

The local HTML preview does not launch Playwright. Browser automation is reserved for platform operations that currently require an editor-backed session.

## Safety model

- Every live create or update requires `--execute` and exact confirmation values.
- Topics are resolved immediately before create; updates bind Post ID, URL, and current-source SHA-256.
- A success marker prevents duplicate creates in the same run directory.
- If a dispatched POST/PUT has no conclusive result, `operation_unknown.json` blocks further writes until platform state is checked.
- Final images must use permanent `/hc/user_images/...` paths.
- Saved responses are sanitized; cookies, CSRF values, JWTs, passwords, and signed upload URLs are not retained.
- `.env`, `.forum-runs/`, browser caches, and generated local assets are ignored by Git.

## Dependencies and reproducibility

- Python 3.11+
- Dependency declaration: [pyproject.toml](pyproject.toml)
- Canonical lock: [uv.lock](uv.lock)
- pip entry point: [requirements.txt](requirements.txt)
- pip resolved versions: [requirements.lock.txt](requirements.lock.txt)
- Playwright browser: required only for image registration or browser-backed updates and installed by `scripts/install_browser.py`

Locked core packages:

| Package | Version | Purpose |
|---|---:|---|
| `beautifulsoup4` | 4.15.0 | HTML normalization, component handling, and readback analysis |
| `mistune` | 3.3.4 | Markdown conversion |
| `requests` | 2.34.2 | BRAIN authentication and browserless HTTP publishing |
| `playwright` | 1.62.0 | Image-editor sessions and browser-backed updates |

## Documentation

- [SKILL.md](SKILL.md): triggering, core workflow, and safety invariants
- [Agent operator guide](references/agent-guide.md): setup, route selection, command contracts, artifacts, and troubleshooting
- [Platform architecture](references/platform-architecture.md): BRAIN authentication, Support SSO, Zendesk, CSRF, and User Images
- [Platform workflow](references/platform-workflow.md): operational checklists
- [HTML compatibility](references/compatibility.md): stable components and sanitizer boundaries
- [Capabilities](references/capabilities.json): machine-readable support matrix
- [Acceptance](references/acceptance.md): release-quality gates

## License

MIT. See [LICENSE](LICENSE).
