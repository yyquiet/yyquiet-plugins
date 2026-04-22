# langfuse-config

用于配置将 Claude Code trace 上报到 Langfuse 的插件。

## 依赖

- `node`
- 首次使用前执行 `/langfuse-config:install`，命令会在插件目录中安装 Node 运行依赖

## 配置环境变量

可直接在 Claude Code 中执行 `/langfuse-config:install`，按提示写入配置。

如需移除配置，可执行 `/langfuse-config:uninstall`。

如果你想手动配置，也可以把以下内容加入 `~/.claude/settings.local.json`：

```json
{
  "env": {
    "TRACE_TO_LANGFUSE": "true",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-...",
    "LANGFUSE_SECRET_KEY": "sk-lf-...",
    "LANGFUSE_BASE_URL": "https://服务地址"
  }
}
```

## 插件行为

启用插件后，Claude Code 会加载插件内的 `hooks/hooks.json`，并执行：

```bash
node ${CLAUDE_PLUGIN_ROOT}/scripts/langfuse_hook.js
```
