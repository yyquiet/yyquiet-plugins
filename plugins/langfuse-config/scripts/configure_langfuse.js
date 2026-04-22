#!/usr/bin/env node

const { configureSettings, refreshRuntimeConfig } = require("./settings");

function parseArgs(argv) {
  const args = {};

  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    const value = argv[index + 1];

    if (key === "--public-key") {
      args.publicKey = value;
      index += 1;
      continue;
    }

    if (key === "--secret-key") {
      args.secretKey = value;
      index += 1;
      continue;
    }

    if (key === "--base-url") {
      args.baseUrl = value;
      index += 1;
    }
  }

  return args;
}

function main(argv = process.argv.slice(2)) {
  const config = refreshRuntimeConfig();
  const args = parseArgs(argv);

  console.log("==> 配置 Langfuse 环境变量...");

  if (!args.publicKey || !args.secretKey || !args.baseUrl) {
    console.log("必须提供 public key、secret key 和 base URL。");
    return 1;
  }

  configureSettings({
    settingsFile: config.settingsFile,
    publicKey: args.publicKey,
    secretKey: args.secretKey,
    baseUrl: args.baseUrl,
  });

  console.log(`已写入配置到 ${config.settingsFile}`);
  return 0;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = {
  main,
  parseArgs,
};
