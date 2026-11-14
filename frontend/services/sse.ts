/**
 * Minimal Server-Sent Events reader built on fetch, because the browser EventSource cannot send an Authorization header.
 */
export interface SseMessage {
  event: string;
  data: unknown;
  id?: string;
}

/** Parse a buffer into complete messages. Returns the unconsumed remainder. Pure, unit tested. */
export function parseSseBuffer(buffer: string): { messages: SseMessage[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const messages: SseMessage[] = [];
  for (const block of blocks) {
    if (block.trim() === "") continue;
    let event = "message";
    let id: string | undefined;
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue;
      const idx = line.indexOf(":");
      const field = idx === -1 ? line : line.slice(0, idx);
      const value = idx === -1 ? "" : line.slice(idx + 1).replace(/^ /, "");
      if (field === "event") event = value;
      else if (field === "id") id = value;
      else if (field === "data") dataLines.push(value);
    }
    if (dataLines.length === 0) continue;
    const raw = dataLines.join("\n");
    let data: unknown = raw;
    try {
      data = JSON.parse(raw);
    } catch {
      /* keep raw text */
    }
    messages.push({ event, data, id });
  }
  return { messages, rest };
}

/** Reads one connection. Returns the last event id seen and whether a terminal `end` or `error` event arrived. */
export async function streamEvents(
  url: string,
  token: string | null,
  onMessage: (m: SseMessage) => void,
  signal: AbortSignal,
  lastEventId?: string,
): Promise<{ lastEventId?: string; finished: boolean }> {
  const res = await fetch(url, {
    headers: {
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
    },
    signal,
    cache: "no-store",
  });
  if (!res.ok || !res.body) throw new Error(`event stream failed with status ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let last = lastEventId;
  let finished = false;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseBuffer(buffer);
    buffer = parsed.rest;
    for (const m of parsed.messages) {
      if (m.id !== undefined) last = m.id;
      if (m.event === "end" || m.event === "error") finished = true;
      onMessage(m);
    }
  }
  return { lastEventId: last, finished };
}

export const RECONNECT_DELAY_MS = 2000;
/** Consecutive failed connection attempts tolerated. A connection that opens and later ends normally resets the count. */
export const MAX_CONSECUTIVE_FAILURES = 10;

/**
 * The server closes each connection after a short time (event `timeout`). Reconnect with Last-Event-ID until `end`.
 * Planned reconnects are unlimited, so a run of any length is followed. Only consecutive errors (network failure or
 * non-2xx) are bounded.
 */
export async function streamWithReconnect(
  url: string,
  token: string | null,
  onMessage: (m: SseMessage) => void,
  signal: AbortSignal,
  delayMs: number = RECONNECT_DELAY_MS,
  connect: typeof streamEvents = streamEvents,
): Promise<void> {
  let last: string | undefined;
  let failures = 0;
  while (!signal.aborted) {
    try {
      const r = await connect(url, token, onMessage, signal, last);
      failures = 0;
      last = r.lastEventId ?? last;
      if (r.finished) return;
    } catch (err) {
      if (signal.aborted) return;
      failures++;
      if (failures > MAX_CONSECUTIVE_FAILURES) throw err;
    }
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
}
