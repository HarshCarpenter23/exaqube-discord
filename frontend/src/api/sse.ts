import type { StageEvent } from "../types";

export interface StreamHandlers {
  onEvent: (ev: StageEvent) => void;
  onError: (message: string, traceId?: string) => void;
  onIncomplete: () => void; // stream ended without a `done` event
  onClose: () => void;
}

/** Parse one SSE frame ("event: x\ndata: {...}") into a StageEvent. */
function parseFrame(frame: string): StageEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith(":")) continue; // comment / heartbeat
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

/**
 * POST a chat message and stream the SSE stages. EventSource can't POST, so we
 * read the response body ourselves. Handles a 500 (error envelope), a stream
 * that dies before `done`, and cancellation via the AbortSignal.
 */
export async function streamChat(
  message: string,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name !== "AbortError") handlers.onError("Could not reach the server.");
    handlers.onClose();
    return;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    handlers.onError(body?.error?.message ?? `Request failed (${res.status})`, body?.error?.trace_id);
    handlers.onClose();
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawDone = false;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const ev = parseFrame(frame);
        if (!ev) continue;
        handlers.onEvent(ev);
        if (ev.event === "done") sawDone = true;
        if (ev.event === "error") handlers.onError(String(ev.data.message ?? "Agent error."));
      }
    }
    if (!sawDone) handlers.onIncomplete();
  } catch (e) {
    if ((e as Error).name !== "AbortError") handlers.onIncomplete();
  } finally {
    handlers.onClose();
  }
}
