#!/usr/bin/env node

const { configureSettings, refreshRuntimeConfig } = require("./settings");

function main() {
  const config = refreshRuntimeConfig();
  removeSettings({ settingsFile: config.settingsFile });
  console.log(`已从 ${config.settingsFile} 中移除 Langfuse 环境变量`);
  return 0;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  main,
};
