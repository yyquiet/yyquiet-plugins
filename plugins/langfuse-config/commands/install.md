# langfuse:install

按下面流程配置 Langfuse 环境变量：

1. 先执行：
```bash
cd ${CLAUDE_PLUGIN_ROOT} && npm install --omit=dev
```

2. 再询问用户这 3 个值：
   - `LANGFUSE_PUBLIC_KEY`
   - `LANGFUSE_SECRET_KEY`
   - `LANGFUSE_BASE_URL`

3. 拿到值后执行：
```bash
node ${CLAUDE_PLUGIN_ROOT}/scripts/configure_langfuse.js \
  --public-key "<LANGFUSE_PUBLIC_KEY>" \
  --secret-key "<LANGFUSE_SECRET_KEY>" \
  --base-url "<LANGFUSE_BASE_URL>"
```

4. 告诉用户配置已写入 `~/.claude/settings.local.json`
