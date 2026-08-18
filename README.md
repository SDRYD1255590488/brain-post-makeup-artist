# BRAIN Post Makeup Artist

中文 | [English](#english)

## 让论坛帖子更好读，也更放心地发布

`brain-post-makeup-artist` 帮你把一个想法、笔记、研究材料或现有草稿，变成适合 WorldQuant BRAIN Support 论坛阅读的帖子：先讲清结论，再组织证据；让结构、重点和细节都容易找到。

它不只是换颜色或套模板。Skill 会根据读者和发帖目标组织标题、摘要、章节与阅读路径，再使用经过平台验证的组件完成排版，并在发布前审计、预览和回读。

### 你会得到什么

- 清晰的帖子结构：摘要、章节、目录和返回顶部链接
- 易读的视觉组件：提示框、表格、指标面板、时间线、图片、公式和折叠详情
- 支持从纯文本、Markdown、HTML 或既有帖子开始
- 桌面、平板和手机预览
- 发布前的兼容性与敏感信息检查
- 图片注册、发布后回读和结构核对
- 对创建、更新和不确定结果的保护，避免误发或重复发帖

所有样式均以 BRAIN Support 论坛的实际回读结果为依据。

### 如何使用

在你使用的 Agent 中安装或提供本目录为 Skill 后，直接描述你要发什么：

```text
我要在 BRAIN 论坛写一篇给新手看的帖子，解释 XXX。

材料：……
读者看完应该能够：……
```

如果已有草稿，也可以直接说：

```text
保留原意，把这篇 Markdown 排版成清晰、专业的 BRAIN 论坛帖子；先预览，未经我确认不要发布。
```

Skill 会在真实发布前确认标题、目标版块和最终正文。它适用于能够读取 `SKILL.md`、运行本地命令、读写文件并向用户请求确认的 Agent；不同 Agent 产品只是在安装或加载 Skill 的方式上不同。

### 安装与首次检查

克隆仓库后，在仓库目录运行：

```bash
uv sync
uv run playwright install chromium
```

然后创建本地 `.env`。如果机器已有 `brain-mcp-v2` 的本地配置，可安全导入：

```bash
uv run python scripts/configure_env.py
```

否则根据 `.env.example` 创建 `.env`，填写自己的 BRAIN 账号信息。`.env` 不会被提交。

最后检查认证与浏览器：

```bash
uv run python scripts/forum_skill.py doctor --auth --browser
```

需要手动运行流程时，可从“撰写 → 审计 → 预览”开始：

```bash
uv run python scripts/forum_skill.py compose \
  --input draft.md --title "帖子标题" --theme emerald \
  --output-dir .forum-runs/my-post

uv run python scripts/forum_skill.py audit \
  --html .forum-runs/my-post/post.html --strict

uv run python scripts/forum_skill.py preview \
  --html .forum-runs/my-post/post.html \
  --output-dir .forum-runs/my-post/preview
```

详细的发布和更新约束见 [SKILL.md](SKILL.md)。

### 安全发布

- 不会自动进行真实发布；每次创建或更新都需要明确确认。
- 图片只使用已注册的 BRAIN User Image，不使用外链或临时上传地址。
- 密码、Cookie、Token、CSRF 和本地运行证据不会提交到仓库。
- 如果一次写入的结果不明确，流程会停止，等待核对平台状态，而不会盲目重试。

### 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- 与锁定 Playwright 版本匹配的 Chromium（执行上面的安装命令）
- 可访问 BRAIN Support 的有效 BRAIN 账号

核心依赖已锁定在 `uv.lock`；也提供 `requirements.txt` 给 pip 用户。详细的组件兼容性和平台工作流位于 `references/`。

## English

## Make forum posts easier to read—and safer to publish

`brain-post-makeup-artist` turns an idea, notes, research material, or an existing draft into a WorldQuant BRAIN Support forum post that is easy to follow: lead with the conclusion, organise the evidence, and make key details easy to find.

It is more than a colour theme or a template. The Skill helps an agent shape the title, summary, sections, and reading flow for the intended audience, then uses platform-tested components and verifies the result before and after publishing.

### What you get

- Clear post structure: summary, sections, navigation, and back-to-top links
- Readable visual components: callouts, tables, KPI panels, timelines, images, formulas, and foldouts
- Start from plain text, Markdown, HTML, or an existing post
- Desktop, tablet, and mobile previews
- Compatibility and sensitive-content checks before publication
- Image registration, post readback, and structural verification
- Guards against accidental, duplicate, or uncertain live writes

All styles are based on real BRAIN Support forum readbacks.

### Use it with your agent

Install or provide this directory as a Skill to your agent, then describe the post you want:

```text
I want to write a beginner-friendly BRAIN forum post explaining XXX.

Source material: …
After reading, readers should be able to: …
```

For an existing draft, ask for a controlled rewrite:

```text
Keep the meaning, turn this Markdown into a clear and professional BRAIN forum post, preview it first, and do not publish without my confirmation.
```

The Skill confirms the title, destination topic, and final body before any live write. It works with agents that can read `SKILL.md`, run local commands, read and write files, and request user confirmation. Skill installation/loading differs by agent product.

### Install and first check

After cloning the repository, run this inside it:

```bash
uv sync
uv run playwright install chromium
```

Create a local `.env` next. If the machine already has a local `brain-mcp-v2` configuration, import it safely:

```bash
uv run python scripts/configure_env.py
```

Otherwise create `.env` from `.env.example` and fill in the user's own BRAIN account details. `.env` is never committed.

Then check authentication and the browser:

```bash
uv run python scripts/forum_skill.py doctor --auth --browser
```

For a manual workflow, begin with compose, audit, and preview:

```bash
uv run python scripts/forum_skill.py compose \
  --input draft.md --title "Post title" --theme emerald \
  --output-dir .forum-runs/my-post

uv run python scripts/forum_skill.py audit \
  --html .forum-runs/my-post/post.html --strict

uv run python scripts/forum_skill.py preview \
  --html .forum-runs/my-post/post.html \
  --output-dir .forum-runs/my-post/preview
```

See [SKILL.md](SKILL.md) for the guarded publishing and update workflow.

### Publish safely

- Live publishing is never automatic; every create or update needs explicit confirmation.
- Images must be registered BRAIN User Images—not external or temporary upload URLs.
- Passwords, cookies, tokens, CSRF values, and local run evidence are never committed.
- If the result of a write is uncertain, the workflow stops for a platform check instead of retrying blindly.

### Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Chromium matched to the locked Playwright version (install it with the command above)
- A valid BRAIN account with access to BRAIN Support

Core dependencies are locked in `uv.lock`; `requirements.txt` is also available for pip users. Component compatibility and platform workflow details live in `references/`.

## License

MIT. See [LICENSE](LICENSE).
