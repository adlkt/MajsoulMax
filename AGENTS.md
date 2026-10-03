# AGENTS.md

## Git 提交规范

- Commit message 采用基于 Conventional Commits 的自定义格式，并在提交类型前增加日期时间：
  `YYYY 年 M 月 D 日 HH:mm <type>[(scope)]：<描述>`
- `<type>` 根据改动语义选择，不强制限制为固定集合。常用类型包括：
  `feat`、`fix`、`docs`、`style`、`refactor`、`perf`、`test`、`build`、`ci`、`chore`、`revert`、`add` 等。
- `(scope)` 可选，用于说明改动涉及的模块或范围。
- 类型与描述之间使用中文全角冒号 `：`。
- 描述应简洁、明确，准确说明本次提交的主要改动。

示例：

- `2026 年 8 月 22 日 13:33 perf：首页加载优化`
- `2026 年 9 月 17 日 17:29 feat(auth)：增加登录状态持久化`
- `2026 年 9 月 17 日 18:05 fix(playwright)：修复登录测试偶发超时`

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Domain docs

single-context layout: root `GLOSSARY.md` and `docs/adr/`. See `docs/agents/domain.md`.
