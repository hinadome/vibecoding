import test from "node:test";
import assert from "node:assert/strict";

import {
  buildA2aCalls,
  buildMcpCalls,
  parseSseEvent,
  toReadableRequestError,
  validateAttachedFiles,
} from "../lib/stock-assistant-helpers.mjs";

test("parseSseEvent parses JSON event payload", () => {
  const parsed = parseSseEvent('event: chunk\ndata: {"content":"hello"}\n\n');
  assert.equal(parsed?.event, "chunk");
  assert.equal(parsed?.data?.content, "hello");
});

test("parseSseEvent returns raw string when data is not JSON", () => {
  const parsed = parseSseEvent("event: message\ndata: plain-text\n\n");
  assert.equal(parsed?.event, "message");
  assert.equal(parsed?.data, "plain-text");
});

test("buildMcpCalls filters incomplete rows and parses arguments", () => {
  const rows = [
    { server: "market-mcp", tool: "get_company_snapshot", argumentsJson: '{"ticker":"NVDA"}' },
    { server: "", tool: "ignored", argumentsJson: "{}" },
  ];
  const calls = buildMcpCalls(rows);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].server, "market-mcp");
  assert.equal(calls[0].arguments.ticker, "NVDA");
});

test("buildA2aCalls filters incomplete rows and parses context", () => {
  const rows = [
    { agent: "risk-agent", task: "check risk", contextJson: '{"horizon_days":90}' },
    { agent: "risk-agent", task: "", contextJson: "{}" },
  ];
  const calls = buildA2aCalls(rows);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].agent, "risk-agent");
  assert.equal(calls[0].context.horizon_days, 90);
});

test("validateAttachedFiles rejects unsupported extension", () => {
  const error = validateAttachedFiles([{ name: "bad.exe", size: 1000 }]);
  assert.ok(error?.includes("Unsupported file type"));
});

test("validateAttachedFiles accepts valid files", () => {
  const error = validateAttachedFiles([{ name: "brief.pdf", size: 1024 }]);
  assert.equal(error, null);
});

test("toReadableRequestError returns network-focused message for TypeError", () => {
  const message = toReadableRequestError(new TypeError("Load failed"), "http://localhost:8000");
  assert.ok(message.includes("Network request failed"));
  assert.ok(message.includes("http://localhost:8000"));
});
