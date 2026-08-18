# BRAIN Post Makeup Artist

中文 | [English](#english)

## 中文介绍

`brain-post-makeup-artist` 是一个用于 WorldQuant BRAIN Support / Zendesk Community 论坛的**帖子结构设计、确定性排版、审计、发布和回读**通用 Agent Skill。

它有两层：任意兼容 Agent 根据用户的发帖目标和素材组织草稿；本仓库的脚本把一个本地 UTF-8 `text`、Markdown 或 HTML 文件稳定转换为论坛兼容 HTML，并负责审计、预览、图片注册、发布与回读。所有组件都基于论坛实际回读结果，而不是仅凭浏览器预览推测。

这意味着“我想发一篇解释 XXX 的帖子，材料如下”是有效的 **Skill 输入**，但不是 CLI 的直接输入：Agent 先把意图和素材写成草稿文件，再调用 `compose`。CLI 不调用大模型，也不会自行补造事实、数据或章节。

兼容 Agent 的最低能力是：能读取 `SKILL.md`、读写本地文件、运行 Python/UV 命令，并在真实发布前向用户取得确认。仓库不依赖某个 Agent 品牌；各产品的“Skill 安装/发现”方式不同，但都可把本目录作为工作指令与脚本包使用。

### 主要能力

- 在 Agent 层，根据发帖目标、受众与素材设计标题、摘要、章节和阅读路径
- CLI 自动识别或显式接收 `text`、Markdown、HTML；Markdown 支持表格、删除线和代码块
- 移除/降级正文 `h1`、去掉 `class`，以平台标题为唯一标题；有两个及以上 `h2` 时生成目录、命名锚点和“返回顶部”链接
- 为首段、标题、引用、表格、代码和分隔线施加三套固定主题之一：`emerald`、`indigo`、`coral`
- 将已注册的本地图片替换为带说明文字的 `<figure>`；未映射为 `/hc/user_images/...` 的图片会被拒绝
- 提供可手工拷入草稿的提示框、状态徽章、KPI 面板、进度条、时间线、折叠区、公式和导航组件
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

在任意兼容 Agent 中可以直接这样说：

```text
我要在 BRAIN 论坛发一篇给新手看的帖子：解释 XXX。
核心材料是：……
希望读者看完能：……
```

Skill 先确认受众、目标、标题、发布版块与改写深度，并把素材发展为草稿。若已有草稿，也可以说“保留原意，只帮我把这篇 Markdown/HTML 排版成论坛帖”。只有在用户确认最终标题、目标版块和正文后，Skill 才能执行真实发布。

命令行层的输入与职责如下：

| 输入 | CLI 实际行为 |
| --- | --- |
| `*.txt` 或 `--input-type text` | 按空行分段，保存为 `post.md` 后转换 |
| `*.md` / `*.markdown` | 解析 Markdown 表格、删除线和代码块后转换 |
| `*.html` / `*.htm` | 保留 HTML 内容并删除 `class`、规范化标题 |
| 图片 | 必须先经 `upload` 注册，再以 `image-map.json` 传给 `compose` |

`--mode preserve|polish|develop` 会写入 `post-spec.json` 记录上层编辑意图；文字的保留、润色或扩写由 Codex 在生成输入草稿时完成，`compose` 不根据该参数改写文字。

命令行使用前，必须安装与锁定 Python Playwright 版本匹配的 Chromium：

```bash
uv sync
uv run playwright install chromium
```

若本机已有 `brain-mcp-v2` 的受限配置，可安全导入凭据：

```bash
uv run python scripts/configure_env.py
```

否则按 `.env.example` 创建本地 `.env` 并填写自己的 BRAIN 凭据。然后验证认证与浏览器：

```bash
uv run python scripts/forum_skill.py doctor --auth --browser
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

Playwright Python 包和浏览器二进制是两件事；**bundled Chromium 是默认且必需的发布前置条件**：

```bash
uv run playwright install chromium
```

默认 `BRAIN_FORUM_CHROME_CHANNEL=chromium`，以保证浏览器版本与锁定的 Python 包匹配。仅当用户明确选择兼容模式时，才设置为 `auto`，让其在 bundled Chromium 缺失时使用系统 Chrome；这不是默认路径，也不会在启动失败后自动重试。

## English

`brain-post-makeup-artist` is an agent-agnostic Skill for **post structuring, deterministic formatting, auditing, publishing, and readback** on WorldQuant BRAIN Support / Zendesk Community forums.

It has two layers: a compatible agent turns a user's posting goal and source materials into a draft; the scripts in this repository deterministically turn one local UTF-8 `text`, Markdown, or HTML file into forum-compatible HTML, then audit, preview, register images, publish, and read it back. Components are based on saved platform readbacks, not on browser previews alone.

In other words, “I want to post a guide about XXX; here are my materials” is a valid **Skill input**, but not a direct CLI input. The agent writes the draft first and then runs `compose`. The CLI does not call an LLM and does not invent facts, figures, or sections.

A compatible agent must be able to read `SKILL.md`, read and write local files, run Python/UV commands, and obtain user confirmation before a live post. The repository does not depend on an agent brand. Skill discovery and installation are product-specific, but any such agent can use this directory as the instruction and script bundle.

### Features

- At the agent layer, plan title, summary, sections, and reading flow from a goal, audience, and materials
- Accept or auto-detect `text`, Markdown, and HTML; Markdown supports tables, strikethrough, and fenced code blocks
- Remove/demote body `h1`, remove `class`, and generate a table of contents, named anchors, and back-to-top links when there are at least two `h2` headings
- Apply one of three fixed themes—`emerald`, `indigo`, or `coral`—to the lead paragraph, headings, quotes, tables, code, and rules
- Replace mapped local images with captioned `<figure>` elements; reject images without a final `/hc/user_images/...` mapping
- Include copy-ready callout, badge, KPI, progress, timeline, foldout, formula, and navigation snippets
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

In any compatible agent, a request can be as simple as:

```text
I want to post a beginner-friendly BRAIN forum guide about XXX.
My source material is: …
Readers should be able to: …
```

The Skill first clarifies audience, goal, title, target topic, and editing depth, then develops the materials into a draft. For an existing draft, ask it to preserve the meaning and format the Markdown or HTML as a forum post instead. A live write requires confirmation of the exact title, topic, and final body.

The command-line inputs and responsibilities are:

| Input | Actual CLI behavior |
| --- | --- |
| `*.txt` or `--input-type text` | Split paragraphs on blank lines, save `post.md`, then convert it |
| `*.md` / `*.markdown` | Convert Markdown tables, strikethrough, and fenced code blocks |
| `*.html` / `*.htm` | Keep the HTML content while stripping `class` and normalizing headings |
| Images | Register with `upload` first, then pass the resulting `image-map.json` to `compose` |

`--mode preserve|polish|develop` is recorded in `post-spec.json` as the intended upstream editing policy. Preservation, polishing, or development of prose is done by Codex when it creates the input draft; `compose` does not rewrite prose based on that flag.

For command-line use, first install the Chromium version matched to the locked Python Playwright package:

```bash
uv sync
uv run playwright install chromium
```

If the machine already has a restricted `brain-mcp-v2` configuration, import credentials safely:

```bash
uv run python scripts/configure_env.py
```

Otherwise create a local `.env` from `.env.example` and fill in the user's own BRAIN credentials. Then verify both authentication and the browser:

```bash
uv run python scripts/forum_skill.py doctor --auth --browser
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

The Playwright Python package and browser binary are separate dependencies. The bundled Chromium is a **required default prerequisite** for publishing:

```bash
uv run playwright install chromium
```

The default `BRAIN_FORUM_CHROME_CHANNEL=chromium` keeps the browser revision matched to the locked Python package. Set it to `auto` only when a user explicitly chooses compatibility mode, allowing system Chrome when bundled Chromium is unavailable; it is not the default path and never retries after a failed launch.

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
