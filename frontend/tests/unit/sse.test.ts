import { describe, expect, it } from "vitest";
import { parseSseBuffer } from "@/services/sse";

describe("parseSseBuffer", () => {
  it("parses complete events and keeps the partial remainder", () => {
    const buf = 'id: 1\nevent: progress\ndata: {"status":"running","completed":2}\n\nevent: end\ndata: {"sta';
    const { messages, rest } = parseSseBuffer(buf);
    expect(messages).toHaveLength(1);
    expect(messages[0]).toEqual({ event: "progress", id: "1", data: { status: "running", completed: 2 } });
    expect(rest).toBe('event: end\ndata: {"sta');
  });
  it("handles CRLF, comments and non JSON data", () => {
    const { messages } = parseSseBuffer(": keepalive\r\n\r\nevent: note\r\ndata: hello\r\n\r\n");
    expect(messages).toEqual([{ event: "note", id: undefined, data: "hello" }]);
  });
  it("defaults the event name to message and skips blocks without data", () => {
    const { messages } = parseSseBuffer("data: 1\n\nid: 5\n\n");
    expect(messages).toEqual([{ event: "message", id: undefined, data: 1 }]);
  });
});
