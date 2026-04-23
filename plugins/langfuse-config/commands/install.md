# langfuse:install

按下面流程配置 Langfuse 环境变量：

1. 先执行：
```bash
cd ${CLAUDE_PLUGIN_ROOT} && npm install --omit=dev
```

2. 再询问用户这 4 个值：
   - `LANGFUSE_PUBLIC_KEY`: pk-lf-...
   - `LANGFUSE_SECRET_KEY`: sk-lf-...
   - `LANGFUSE_BASE_URL`: https://服务地址
   - `LANGFUSE_USER_ID`: your-user-id，使用名字拼音如liyuan

3. 拿到值后执行：
```bash
node ${CLAUDE_PLUGIN_ROOT}/scripts/configure_langfuse.js \
  --public-key "<LANGFUSE_PUBLIC_KEY>" \
  --secret-key "<LANGFUSE_SECRET_KEY>" \
  --base-url "<LANGFUSE_BASE_URL>" \
  --user-id "<LANGFUSE_USER_ID>"
```

4. 告诉用户配置已写入 `~/.claude/settings.local.json`
