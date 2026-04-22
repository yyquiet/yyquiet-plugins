#!/usr/bin/env node

const crypto = require("node:crypto");
const { ObservationType } = require("@langfuse/core");

const {
  extractText,
  getContent,
  getMessageTimestamp,
  getModel,
  sumUsageDetails,
  truncateText,
} = require("./collector");

function makeId(parts) {
  return crypto.createHash("sha256").update(parts.join("::"), "utf8").digest("hex").slice(0, 32);
}

function toIso(value) {
  return value instanceof Date ? value.toISOString() : undefined;
}

function buildIngestionBatch({ sessionId, turnNum, turn, transcriptPath }) {
  const userTextRaw = extractText(getContent(turn.userMsg));
  const [userText, userTextMeta] = truncateText(userTextRaw);
  const model = getModel(turn.assistantMsgs[0] || {});
  const usageDetails = sumUsageDetails(turn.assistantMsgs);
  const traceTimestamp =
    getMessageTimestamp(turn.userMsg) ||
    turn.events.find((event) => event.timestamp)?.timestamp ||
    new Date();
  const traceEndTime =
    [...turn.events].reverse().find((event) => event.timestamp)?.timestamp || traceTimestamp;
  const traceId = makeId([sessionId, String(turnNum), transcriptPath]);

  let finalAssistantText = "";
  let finalAssistantTextMeta = null;
  let finalAssistantTimestamp = traceEndTime;
  let finalAssistantIndex = -1;

  turn.events.forEach((event, index) => {
    if (event.kind === "assistant_text" && event.text) {
      finalAssistantIndex = index;
      finalAssistantText = event.text;
      finalAssistantTextMeta = event.textMeta || null;
      finalAssistantTimestamp = event.timestamp || traceEndTime;
    }
  });

  const batch = [
    {
      id: makeId([traceId, "trace-create"]),
      type: "trace-create",
      timestamp: toIso(traceTimestamp),
      body: {
        id: traceId,
        timestamp: toIso(traceTimestamp),
        name: `Claude Code - Turn ${turnNum}`,
        input: { role: "user", content: userText },
        output: { role: "assistant", content: finalAssistantText },
        sessionId,
        metadata: {
          source: "claude-code",
          session_id: sessionId,
          turn_number: turnNum,
          transcript_path: transcriptPath,
          user_text: userTextMeta,
        },
        tags: ["claude-code"],
      },
    },
  ];

  turn.events.forEach((event, index) => {
    const eventId = makeId([traceId, String(index), event.kind]);
    if (event.kind === "assistant_text") {
      if (index === finalAssistantIndex) {
        batch.push({
          id: makeId([eventId, "generation-create"]),
          type: "generation-create",
          timestamp: toIso(event.timestamp || finalAssistantTimestamp),
          body: {
            id: eventId,
            traceId,
            name: "Claude Response",
            startTime: toIso(event.timestamp || finalAssistantTimestamp),
            endTime: toIso(event.timestamp || finalAssistantTimestamp),
            completionStartTime: toIso(event.timestamp || finalAssistantTimestamp),
            model,
            input: { role: "user", content: userText },
            output: { role: "assistant", content: event.text },
            metadata: {
              assistant_text: finalAssistantTextMeta,
              tool_count: turn.events.filter((item) => item.kind === "tool_call").length,
              usage_details: Object.keys(usageDetails).length > 0 ? usageDetails : null,
            },
            usageDetails: Object.keys(usageDetails).length > 0 ? usageDetails : undefined,
          },
        });
        return;
      }

      batch.push({
        id: makeId([eventId, "event-create"]),
        type: "event-create",
        timestamp: toIso(event.timestamp || traceTimestamp),
        body: {
          id: eventId,
          traceId,
          name: "Assistant Message",
          startTime: toIso(event.timestamp || traceTimestamp),
          input: { role: "assistant", content: event.text },
          metadata: {
            assistant_text: event.textMeta || null,
            phase: "pre_tool_or_intermediate",
            observation_kind: "assistant_text",
          },
        },
      });
      return;
    }

    if (event.kind === "tool_call") {
      batch.push({
        id: makeId([eventId, "span-create"]),
        type: "span-create",
        timestamp: toIso(event.timestamp || traceTimestamp),
        body: {
          id: eventId,
          traceId,
          name: `Tool: ${event.name}`,
          startTime: toIso(event.timestamp || traceTimestamp),
          endTime: toIso(event.timestamp || traceTimestamp),
          input: event.input,
          output: event.toolId ? turn.toolResultsById[event.toolId] : undefined,
          metadata: {
            tool_name: event.name,
            tool_id: event.toolId,
          },
          level: "DEFAULT",
          type: ObservationType.Tool,
        },
      });
      return;
    }

    if (event.kind === "tool_result") {
      batch.push({
        id: makeId([eventId, "event-create"]),
        type: "event-create",
        timestamp: toIso(event.timestamp || traceTimestamp),
        body: {
          id: eventId,
          traceId,
          name: "Tool Result",
          startTime: toIso(event.timestamp || traceTimestamp),
          output: event.output,
          metadata: {
            tool_id: event.toolId,
            output_meta: event.outputMeta || null,
            observation_kind: "tool_result",
          },
        },
      });
    }
  });

  return batch;
}

async function emitTurn(langfuse, sessionId, turnNum, turn, transcriptPath) {
  const batch = buildIngestionBatch({
    sessionId,
    turnNum,
    turn,
    transcriptPath: String(transcriptPath),
  });
  await langfuse.api.ingestion.batch({ batch });
}

module.exports = {
  buildIngestionBatch,
  emitTurn,
};
