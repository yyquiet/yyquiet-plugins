#!/usr/bin/env node

const { LangfuseClient } = require("@langfuse/client");

const {
  FileLock,
  buildTurns,
  debug,
  extractSessionAndTranscript,
  info,
  loadSessionState,
  loadState,
  readHookPayload,
  readNewJsonl,
  saveState,
  setCurrentSessionId,
  stateKey,
  writeSessionState,
} = require("./collector");
const { refreshRuntimeConfig } = require("./settings");
const { emitTurn } = require("./reporter");

async function main() {
  const start = Date.now();
  const config = refreshRuntimeConfig();
  setCurrentSessionId("");
  debug("Hook started");

  if (!config.traceEnabled) {
    debug("trace not enabled");
    return 0;
  }

  if (!config.publicKey || !config.secretKey || !config.baseUrl) {
    debug("missing public_key or secret_key or host");
    return 0;
  }

  const payload = readHookPayload();
  const [sessionId, transcriptPath] = extractSessionAndTranscript(payload);
  if (sessionId) {
    setCurrentSessionId(sessionId);
  }

  if (!sessionId || !transcriptPath) {
    debug("Missing session_id or transcript_path from hook payload; exiting.");
    return 0;
  }

  let langfuse;
  try {
    langfuse = new LangfuseClient({
      publicKey: config.publicKey,
      secretKey: config.secretKey,
      baseUrl: config.baseUrl,
    });
  } catch (error) {
    debug(`Langfuse init failed: ${error.message}`);
    return 0;
  }

  try {
    const lock = new FileLock(config.lockFile);
    let emitted = 0;

    await lock.run(async () => {
      const state = loadState();
      const key = stateKey(sessionId, transcriptPath);
      const sessionState = loadSessionState(state, key);
      const [messages, nextState] = readNewJsonl(transcriptPath, sessionState);

      if (messages.length === 0) {
        writeSessionState(state, key, nextState);
        saveState(state);
        return;
      }

      const turns = buildTurns(messages);
      if (turns.length === 0) {
        writeSessionState(state, key, nextState);
        saveState(state);
        return;
      }

      for (const turn of turns) {
        emitted += 1;
        await emitTurn(langfuse, sessionId, nextState.turnCount + emitted, turn, transcriptPath);
      }

      nextState.turnCount += emitted;
      writeSessionState(state, key, nextState);
      saveState(state);
    });

    await langfuse.flush();
    info(`Processed ${emitted} turns in ${((Date.now() - start) / 1000).toFixed(2)}s (session=${sessionId})`);
    return 0;
  } catch (error) {
    debug(`Unexpected failure: ${error.message}`);
    return 0;
  } finally {
    if (langfuse) {
      try {
        await langfuse.shutdown();
      } catch {
        // Shutdown failures should not affect hook completion.
      }
    }
  }
}

if (require.main === module) {
  main().then((code) => {
    process.exitCode = code;
  });
}

module.exports = {
  main,
};
