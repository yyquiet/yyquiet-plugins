#!/usr/bin/env node

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const SETTING_KEYS = {
  TRACE_TO_LANGFUSE: "TRACE_TO_LANGFUSE",
  LANGFUSE_PUBLIC_KEY: "LANGFUSE_PUBLIC_KEY",
  LANGFUSE_SECRET_KEY: "LANGFUSE_SECRET_KEY",
  LANGFUSE_BASE_URL: "LANGFUSE_BASE_URL",
  LANGFUSE_USER_ID: "LANGFUSE_USER_ID",
  LANGFUSE_DEBUG: "LANGFUSE_DEBUG",
  LANGFUSE_MAX_CHARS: "LANGFUSE_MAX_CHARS",
};

const REMOVE_KEYS = [
  SETTING_KEYS.TRACE_TO_LANGFUSE,
  SETTING_KEYS.LANGFUSE_PUBLIC_KEY,
  SETTING_KEYS.LANGFUSE_SECRET_KEY,
  SETTING_KEYS.LANGFUSE_BASE_URL,
  SETTING_KEYS.LANGFUSE_USER_ID,
  SETTING_KEYS.LANGFUSE_DEBUG,
  SETTING_KEYS.LANGFUSE_MAX_CHARS,
];

let runtimeConfig = createRuntimeConfig();

function readSettings(settingsFile) {
  try {
    if (!fs.existsSync(settingsFile)) {
      return {};
    }
    return JSON.parse(fs.readFileSync(settingsFile, "utf8"));
  } catch {
    return {};
  }
}

function writeSettings(settingsFile, settings) {
  fs.mkdirSync(path.dirname(settingsFile), { recursive: true });
  fs.writeFileSync(settingsFile, JSON.stringify(settings, null, 2), "utf8");
}

function createRuntimeConfig({ homeDir = os.homedir(), env = process.env } = {}) {
  const settingsFile = path.join(homeDir, ".claude", "settings.local.json");
  const stateDir = path.join(homeDir, ".claude", "state");
  const logFile = path.join(stateDir, "langfuse_hook.log");
  const stateFile = path.join(stateDir, "langfuse_state.json");
  const lockFile = path.join(stateDir, "langfuse_state.lock");
  const settings = readSettings(settingsFile);
  const settingsEnv = settings && typeof settings.env === "object" ? settings.env : {};
  const readConfigValue = (name) => env[name] || settingsEnv[name] || "";
  const maxChars = Number.parseInt(readConfigValue(SETTING_KEYS.LANGFUSE_MAX_CHARS) || "20000", 10);

  return {
    homeDir,
    settingsFile,
    stateDir,
    logFile,
    stateFile,
    lockFile,
    settingsEnv,
    traceEnabled: readConfigValue(SETTING_KEYS.TRACE_TO_LANGFUSE).toLowerCase() === "true",
    publicKey: readConfigValue(SETTING_KEYS.LANGFUSE_PUBLIC_KEY),
    secretKey: readConfigValue(SETTING_KEYS.LANGFUSE_SECRET_KEY),
    baseUrl: readConfigValue(SETTING_KEYS.LANGFUSE_BASE_URL),
    userId: readConfigValue(SETTING_KEYS.LANGFUSE_USER_ID),
    maxChars: Number.isFinite(maxChars) ? maxChars : 20000,
    debugEnabled: readConfigValue(SETTING_KEYS.LANGFUSE_DEBUG).toLowerCase() === "true",
  };
}

function getRuntimeConfig() {
  return runtimeConfig;
}

function refreshRuntimeConfig(options) {
  runtimeConfig = createRuntimeConfig(options);
  return runtimeConfig;
}

function configureSettings({ settingsFile, publicKey, secretKey, baseUrl, userId }) {
  const settings = readSettings(settingsFile);
  const env = { ...(settings.env || {}) };
  env[SETTING_KEYS.TRACE_TO_LANGFUSE] = "true";
  env[SETTING_KEYS.LANGFUSE_PUBLIC_KEY] = publicKey;
  env[SETTING_KEYS.LANGFUSE_SECRET_KEY] = secretKey;
  env[SETTING_KEYS.LANGFUSE_BASE_URL] = baseUrl;
  env[SETTING_KEYS.LANGFUSE_USER_ID] = userId;
  settings.env = env;
  writeSettings(settingsFile, settings);
}

function removeSettings({ settingsFile }) {
  const settings = readSettings(settingsFile);
  const env = { ...(settings.env || {}) };
  for (const key of REMOVE_KEYS) {
    delete env[key];
  }
  settings.env = env;
  writeSettings(settingsFile, settings);
}

module.exports = {
  REMOVE_KEYS,
  SETTING_KEYS,
  configureSettings,
  createRuntimeConfig,
  getRuntimeConfig,
  readSettings,
  refreshRuntimeConfig,
  removeSettings,
  writeSettings,
};
