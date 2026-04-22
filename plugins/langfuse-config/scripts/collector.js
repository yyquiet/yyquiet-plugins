#!/usr/bin/env node

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { getRuntimeConfig } = require("./settings");

let currentSessionId = "";

class SessionState {
  constructor(offset = 0, buffer = "", turnCount = 0) {
    this.offset = offset;
    this.buffer = buffer;
    this.turnCount = turnCount;
  }
}

function setCurrentSessionId(sessionId) {
  currentSessionId = sessionId || "";
}

function log(level, message) {
  try {
    const config = getRuntimeConfig();
    fs.mkdirSync(config.stateDir, { recursive: true });
    const now = new Date().toISOString().replace("T", " ").slice(0, 19);
    fs.appendFileSync(config.logFile, `${now} [${level}][${currentSessionId}] ${message}\n`, "utf8");
  } catch {
    // Logging must never break the hook flow.
  }
}

function debug(message) {
  if (getRuntimeConfig().debugEnabled) {
    log("DEBUG", message);
  }
}

function info(message) {
  log("INFO", message);
}

function warn(message) {
  log("WARN", message);
}

function error(message) {
  log("ERROR", message);
}

function stateKey(sessionId, transcriptPath) {
  return crypto.createHash("sha256").update(`${sessionId}::${transcriptPath}`, "utf8").digest("hex");
}

function loadState() {
  try {
    const config = getRuntimeConfig();
    if (!fs.existsSync(config.stateFile)) {
      return {};
    }

    return JSON.parse(fs.readFileSync(config.stateFile, "utf8"));
  } catch {
    return {};
  }
}

function saveState(state) {
  try {
    const config = getRuntimeConfig();
    fs.mkdirSync(config.stateDir, { recursive: true });
    const tmpFile = `${config.stateFile}.tmp`;
    fs.writeFileSync(tmpFile, JSON.stringify(state, null, 2), "utf8");
    fs.renameSync(tmpFile, config.stateFile);
  } catch (error) {
    debug(`saveState failed: ${error.message}`);
  }
}

function loadSessionState(globalState, key) {
  const value = globalState[key] || {};
  return new SessionState(Number(value.offset || 0), String(value.buffer || ""), Number(value.turn_count || 0));
}

function writeSessionState(globalState, key, sessionState) {
  globalState[key] = {
    offset: sessionState.offset,
    buffer: sessionState.buffer,
    turn_count: sessionState.turnCount,
    updated: new Date().toISOString(),
  };
}

function readHookPayload(stdin = process.stdin) {
  try {
    const data = fs.readFileSync(stdin.fd, "utf8");
    return data.trim() ? JSON.parse(data) : {};
  } catch {
    return {};
  }
}

function extractSessionAndTranscript(payload) {
  const sessionId = payload.sessionId || payload.session_id || payload.session?.id || null;
  const transcript = payload.transcriptPath || payload.transcript_path || payload.transcript?.path || null;
  return [sessionId, transcript ? path.resolve(transcript) : null];
}

function parseTimestamp(value) {
  if (typeof value !== "string" || !value) {
    return null;
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function getMessageTimestamp(message) {
  return parseTimestamp(message?.timestamp);
}

function getContent(message) {
  if (!message || typeof message !== "object") {
    return null;
  }

  if (message.message && typeof message.message === "object") {
    return message.message.content;
  }

  return message.content;
}

function getRole(message) {
  if (!message || typeof message !== "object") {
    return null;
  }

  if (message.type === "user" || message.type === "assistant") {
    return message.type;
  }

  const role = message.message?.role;
  return role === "user" || role === "assistant" ? role : null;
}

function isToolResult(message) {
  if (getRole(message) !== "user") {
    return false;
  }

  const content = getContent(message);
  return Array.isArray(content) && content.some((item) => item?.type === "tool_result");
}

function iterToolResults(content) {
  return Array.isArray(content) ? content.filter((item) => item?.type === "tool_result") : [];
}

function extractText(content) {
  if (typeof content === "string") {
    return content;
  }

  if (!Array.isArray(content)) {
    return "";
  }

  return content
    .map((item) => {
      if (typeof item === "string") {
        return item;
      }
      if (item?.type === "text") {
        return item.text || "";
      }
      return "";
    })
    .filter(Boolean)
    .join("\n");
}

function truncateText(value, maxChars = getRuntimeConfig().maxChars) {
  const text = value == null ? "" : String(value);
  if (text.length <= maxChars) {
    return [
      text,
      {
        truncated: false,
        orig_len: text.length,
      },
    ];
  }

  const head = text.slice(0, maxChars);
  return [
    head,
    {
      truncated: true,
      orig_len: text.length,
      kept_len: head.length,
      sha256: crypto.createHash("sha256").update(text, "utf8").digest("hex"),
    },
  ];
}

function getModel(message) {
  return message?.message?.model || "claude";
}

function getMessageId(message) {
  const id = message?.message?.id;
  return typeof id === "string" && id ? id : null;
}

function getUsageDetails(message) {
  const usage = message?.message?.usage;
  if (!usage || typeof usage !== "object") {
    return {};
  }

  const mapped = {};
  if (Number.isInteger(usage.input_tokens)) {
    mapped.input = usage.input_tokens;
  }
  if (Number.isInteger(usage.output_tokens)) {
    mapped.output = usage.output_tokens;
  }
  if (Number.isInteger(usage.cache_creation_input_tokens)) {
    mapped.cache_creation_input = usage.cache_creation_input_tokens;
  }
  if (Number.isInteger(usage.cache_read_input_tokens)) {
    mapped.cache_read_input = usage.cache_read_input_tokens;
  }
  return mapped;
}

function sumUsageDetails(messages) {
  const totals = {};
  for (const message of messages) {
    for (const [key, value] of Object.entries(getUsageDetails(message))) {
      totals[key] = (totals[key] || 0) + value;
    }
  }

  if ("input" in totals || "output" in totals) {
    totals.total = (totals.input || 0) + (totals.output || 0);
  }

  return totals;
}

function readNewJsonl(transcriptPath, sessionState) {
  if (!fs.existsSync(transcriptPath)) {
    return [[], sessionState];
  }

  const handle = fs.openSync(transcriptPath, "r");
  try {
    const stats = fs.fstatSync(handle);
    if (sessionState.offset > stats.size) {
      sessionState.offset = 0;
      sessionState.buffer = "";
    }

    const length = Math.max(0, stats.size - sessionState.offset);
    if (length === 0) {
      return [[], sessionState];
    }

    const buffer = Buffer.alloc(length);
    fs.readSync(handle, buffer, 0, length, sessionState.offset);
    sessionState.offset = stats.size;
    const combined = sessionState.buffer + buffer.toString("utf8");
    const lines = combined.split("\n");
    sessionState.buffer = lines.pop() || "";

    const messages = [];
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) {
        continue;
      }

      try {
        messages.push(JSON.parse(line));
      } catch {
        // Skip malformed JSONL records and continue reading later lines.
      }
    }

    return [messages, sessionState];
  } finally {
    fs.closeSync(handle);
  }
}

function normalizeAssistantContent(content) {
  if (Array.isArray(content)) {
    return content;
  }
  if (content) {
    return [{ type: "text", text: String(content) }];
  }
  return [];
}

function newAssistantBlocks(previousBlocks, currentBlocks) {
  let prefixLength = 0;
  const maxPrefix = Math.min(previousBlocks.length, currentBlocks.length);
  while (prefixLength < maxPrefix) {
    if (JSON.stringify(previousBlocks[prefixLength]) !== JSON.stringify(currentBlocks[prefixLength])) {
      break;
    }
    prefixLength += 1;
  }
  return currentBlocks.slice(prefixLength);
}

function assistantEventsFromBlocks(blocks, eventTimestamp) {
  const events = [];

  for (const item of blocks) {
    if (item?.type === "text" && item.text) {
      const [text, textMeta] = truncateText(item.text);
      events.push({
        kind: "assistant_text",
        text,
        textMeta,
        timestamp: eventTimestamp,
      });
      continue;
    }

    if (item?.type === "tool_use") {
      const input = item.input == null ? null : item.input;
      events.push({
        kind: "tool_call",
        toolId: String(item.id || ""),
        name: item.name || "unknown",
        input,
        timestamp: eventTimestamp,
      });
    }
  }

  return events;
}

function buildTurns(messages) {
  const turns = [];
  let currentUser = null;
  let assistantOrder = [];
  let assistantLatest = {};
  let assistantBlocksById = {};
  let toolResultsById = {};
  let events = [];

  const flushTurn = () => {
    if (!currentUser || assistantOrder.length === 0) {
      return;
    }

    turns.push({
      userMsg: currentUser,
      assistantMsgs: assistantOrder.map((id) => assistantLatest[id]).filter(Boolean),
      toolResultsById: { ...toolResultsById },
      events: [...events],
    });
  };

  for (const message of messages) {
    const role = getRole(message);

    if (isToolResult(message)) {
      for (const toolResult of iterToolResults(getContent(message))) {
        const toolId = String(toolResult.tool_use_id || "");
        if (!toolId) {
          continue;
        }

        toolResultsById[toolId] = toolResult.content;
        const rawOutput =
          typeof toolResult.content === "string"
            ? toolResult.content
            : JSON.stringify(toolResult.content ?? "", null, 0);
        const [output, outputMeta] = truncateText(rawOutput);
        events.push({
          kind: "tool_result",
          toolId,
          output,
          outputMeta,
          timestamp: getMessageTimestamp(message),
        });
      }
      continue;
    }

    if (role === "user") {
      flushTurn();
      currentUser = message;
      assistantOrder = [];
      assistantLatest = {};
      assistantBlocksById = {};
      toolResultsById = {};
      events = [];
      continue;
    }

    if (role === "assistant") {
      if (!currentUser) {
        continue;
      }

      const messageId = getMessageId(message) || `noid:${assistantOrder.length}`;
      if (!(messageId in assistantLatest)) {
        assistantOrder.push(messageId);
        assistantBlocksById[messageId] = [];
      }

      assistantLatest[messageId] = message;
      const currentBlocks = normalizeAssistantContent(getContent(message));
      const previousBlocks = assistantBlocksById[messageId] || [];
      const newBlocks = newAssistantBlocks(previousBlocks, currentBlocks);
      assistantBlocksById[messageId] = currentBlocks;
      events.push(...assistantEventsFromBlocks(newBlocks, getMessageTimestamp(message)));
    }
  }

  flushTurn();
  return turns;
}

class FileLock {
  constructor(lockPath, timeoutMs = 2000) {
    this.lockPath = lockPath;
    this.timeoutMs = timeoutMs;
    this.locked = false;
  }

  acquire() {
    fs.mkdirSync(path.dirname(this.lockPath), { recursive: true });
    const deadline = Date.now() + this.timeoutMs;

    while (Date.now() <= deadline) {
      try {
        fs.writeFileSync(this.lockPath, String(process.pid), { flag: "wx" });
        this.locked = true;
        return;
      } catch (error) {
        if (error.code !== "EEXIST") {
          throw error;
        }
      }

      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 50);
    }
  }

  release() {
    if (!this.locked) {
      return;
    }

    try {
      fs.unlinkSync(this.lockPath);
    } catch {
      // Ignore cleanup failures because the lock is already being released.
    }
    this.locked = false;
  }

  async run(fn) {
    this.acquire();
    try {
      return await fn();
    } finally {
      this.release();
    }
  }
}

module.exports = {
  FileLock,
  SessionState,
  buildTurns,
  debug,
  extractSessionAndTranscript,
  extractText,
  getContent,
  getMessageTimestamp,
  getModel,
  info,
  warn,
  error,
  loadSessionState,
  loadState,
  readHookPayload,
  readNewJsonl,
  saveState,
  setCurrentSessionId,
  stateKey,
  sumUsageDetails,
  truncateText,
  writeSessionState,
};
