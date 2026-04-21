# langfuse:install

按下面流程配置 Langfuse 环境变量：

1. 先执行：
```bash
python3 -m pip install langfuse==4.3.1
```

2. 再询问用户这 3 个值：
   - `LANGFUSE_PUBLIC_KEY`
   - `LANGFUSE_SECRET_KEY`
   - `LANGFUSE_BASE_URL`

3. 拿到值后执行：
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/configure_langfuse.py \
  --public-key "<LANGFUSE_PUBLIC_KEY>" \
  --secret-key "<LANGFUSE_SECRET_KEY>" \
  --base-url "<LANGFUSE_BASE_URL>"
```

4. 告诉用户配置已写入 `~/.claude/settings.local.json`
