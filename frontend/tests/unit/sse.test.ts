import { describe, expect, it } from "vitest";
import { MAX_CONSECUTIVE_FAILURES, parseSseBuffer, streamWithReconnect } from "@/services/sse";

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

describe("streamWithReconnect", () => {
  const ok = (finished: boolean, id: string) => ({ lastEventId: id, finished });
  it("keeps reconnecting past 40 planned timeouts and passes Last-Event-ID", async () => {
    const seen: Array<string | undefined> = [];
    let n = 0;
    const connect = async (_u: string, _t: string | null, _m: unknown, _s: AbortSignal, last?: string) => {
      seen.push(last);
      n++;
      return ok(n === 60, String(n));
    };
    await streamWithReconnect("u", null, () => {}, new AbortController().signal, 0, connect as never);
    expect(n).toBe(60);
    expect(seen[0]).toBeUndefined();
    expect(seen[59]).toBe("59");
  });
  it("gives up after consecutive failures and rethrows the error", async () => {
    let n = 0;
    const connect = async () => { n++; throw new Error("down"); };
    await expect(streamWithReconnect("u", null, () => {}, new AbortController().signal, 0, connect as never)).rejects.toThrow("down");
    expect(n).toBe(MAX_CONSECUTIVE_FAILURES + 1);
  });
  it("resets the failure count after a successful connection", async () => {
    let n = 0;
    const connect = async () => {
      n++;
      if (n === 8) return ok(false, "8");
      if (n === 20) return ok(true, "20");
      throw new Error("flaky");
    };
    await streamWithReconnect("u", null, () => {}, new AbortController().signal, 0, connect as never);
    expect(n).toBe(20);
  });
  it("returns quietly when aborted", async () => {
    const ctrl = new AbortController();
    const connect = async () => { ctrl.abort(); throw new Error("aborted"); };
    await streamWithReconnect("u", null, () => {}, ctrl.signal, 0, connect as never);
  });
});
