# yyquiet Claude Plugins

用于托管和分享 Claude Code 插件的仓库。

当前包含的插件：
- `langfuse-config`

## 使用方式

在 Claude Code 中添加 marketplace：

```text
/plugin marketplace add yyquiet/yyquiet-plugins
```

然后安装插件：

```text
/plugin install langfuse-config@yyquiet-plugins
```

## 插件说明

### langfuse-config

用于将 Claude Code 的 trace 上报到 Langfuse。

详细说明见：
- [plugins/langfuse-config/README.md](./plugins/langfuse-config/README.md)
