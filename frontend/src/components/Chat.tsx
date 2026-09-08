import { useRef, useState } from "react";
import Markdown from "react-markdown";
import { api } from "../api/client";
import { streamChat } from "../api/sse";
import type { ChartSpec, StageEvent } from "../types";
import { ChartView } from "./ChartView";
import { DataTable } from "./DataTable";

interface ToolCall { handle: string; name: string; args: Record<string, unknown>; }
interface ToolResult { handle: string; kind: string; payload: Record<string, unknown>; }
interface ToolErr { handle?: string; code: string; message: string; }
interface Assistant {
  reasoning: string;
  tools: ToolCall[];
  progress: Record<string, string>;
  results: ToolResult[];
  errors: ToolErr[];
  message: string;
  status: "streaming" | "done" | "incomplete" | "error";
}
type ChatMessage = { role: "user"; text: string } | { role: "assistant"; turn: Assistant };

const EXAMPLES = [
  "Which channels died after March?",
  "Who are the top 10 posters in the busiest server?",
  "Show weekday vs weekend message volume.",
  "Chart messages per day for the most active server, then export it to Excel.",
];

function emptyAssistant(): Assistant {
  return { reasoning: "", tools: [], progress: {}, results: [], errors: [], message: "", status: "streaming" };
}

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  function updateAssistant(mut: (a: Assistant) => void) {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last?.role === "assistant") {
        const turn = { ...last.turn };
        mut(turn);
        next[next.length - 1] = { role: "assistant", turn };
      }
      return next;
    });
    queueMicrotask(() => logRef.current?.scrollTo(0, logRef.current.scrollHeight));
  }

  function onEvent(ev: StageEvent) {
    const d = ev.data as Record<string, unknown>;
    updateAssistant((a) => {
      switch (ev.event) {
        case "reasoning": a.reasoning += String(d.delta ?? ""); break;
        case "tool_selected":
          a.tools.push({ handle: String(d.handle), name: String(d.name), args: (d.args ?? {}) as Record<string, unknown> });
          break;
        case "tool_progress":
          if (d.handle) a.progress[String(d.handle)] = String(d.message ?? "");
          break;
        case "tool_result":
          a.results.push({ handle: String(d.handle), kind: String(d.kind), payload: d });
          break;
        case "tool_error":
          a.errors.push({ handle: d.handle ? String(d.handle) : undefined, code: String(d.code), message: String(d.message) });
          break;
        case "message": a.message += String(d.delta ?? ""); break;
        case "done": a.status = "done"; break;
      }
    });
  }

  async function send(text: string) {
    if (!text.trim() || streaming) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text }, { role: "assistant", turn: emptyAssistant() }]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    await streamChat(text, {
      onEvent,
      onError: (message, traceId) =>
        updateAssistant((a) => {
          a.errors.push({ code: "error", message: traceId ? `${message} (trace ${traceId})` : message });
          a.status = "error";
        }),
      onIncomplete: () => updateAssistant((a) => { if (a.status === "streaming") a.status = "incomplete"; }),
      onClose: () => setStreaming(false),
    }, controller.signal);
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
  }

  return (
    <div className="chat">
      <div className="chat-log" ref={logRef}>
        {messages.length === 0 && (
          <div className="stack">
            <p className="subtle">Ask a question about the Discord data. For example:</p>
            {EXAMPLES.map((q) => (
              <button key={q} className="btn ghost small" style={{ alignSelf: "flex-start" }} onClick={() => send(q)}>
                {q}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="msg-user">{m.text}</div>
          ) : (
            <div key={i} className="msg-assistant">
              <AssistantView turn={m.turn} />
            </div>
          ),
        )}
      </div>

      <div className="chat-input">
        <textarea
          value={input}
          placeholder="Ask about servers, channels, members, activity…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
          }}
        />
        {streaming ? (
          <button className="btn ghost" onClick={stop}>Stop</button>
        ) : (
          <button className="btn" onClick={() => send(input)} disabled={!input.trim()}>Send</button>
        )}
      </div>
    </div>
  );
}

function AssistantView({ turn }: { turn: Assistant }) {
  return (
    <div className="turn">
      {turn.reasoning && (
        <details className="reasoning-details">
          <summary>Reasoning</summary>
          <div className="reasoning">{turn.reasoning}</div>
        </details>
      )}

      {turn.tools.map((t) => {
        const result = turn.results.find((r) => r.handle === t.handle);
        const err = turn.errors.find((e) => e.handle === t.handle);
        return (
          <div key={t.handle} className="stack" style={{ gap: 6 }}>
            <div className="tool-chip">
              <b>{t.name}</b>
              {typeof t.args.sql === "string" ? <span className="mono">{t.args.sql}</span> : <span className="mono">{JSON.stringify(t.args)}</span>}
            </div>
            {!result && !err && turn.progress[t.handle] && (
              <div className="subtle"><span className="spinner" /> {turn.progress[t.handle]}</div>
            )}
            {result && <ResultView result={result} />}
            {err && <div className="tool-error">✗ [{err.code}] {err.message}</div>}
          </div>
        );
      })}

      {turn.errors.filter((e) => !e.handle).map((e, i) => (
        <div key={i} className="tool-error">✗ {e.message}</div>
      ))}

      {turn.message && (
        <div className="prose">
          <Markdown components={{ a: (props) => <a {...props} target="_blank" rel="noreferrer" /> }}>
            {turn.message}
          </Markdown>
        </div>
      )}

      {turn.status === "streaming" && <div className="subtle"><span className="spinner" /> working…</div>}
      {turn.status === "incomplete" && <div className="banner warn">The response ended early (connection lost).</div>}
    </div>
  );
}

function ResultView({ result }: { result: ToolResult }) {
  if (result.kind === "table") {
    const cols = (result.payload.columns as string[]) ?? [];
    const rows = (result.payload.rows as unknown[][]) ?? [];
    return (
      <div className="card" style={{ padding: 0 }}>
        <DataTable columns={cols} rows={rows} maxRows={8} />
      </div>
    );
  }
  if (result.kind === "chart_spec") {
    return <ChartResult spec={result.payload as unknown as ChartSpec} />;
  }
  if (result.kind === "artifact") {
    return (
      <a className="dl-link" href={String(result.payload.url)} target="_blank" rel="noreferrer">
        ⬇ {String(result.payload.filename)}
      </a>
    );
  }
  return null;
}

function ChartResult({ spec }: { spec: ChartSpec }) {
  const [pinned, setPinned] = useState(false);
  async function pin() {
    await api.createPin({
      title: spec.title ?? "Chart",
      spec: { type: spec.type, x: spec.x, y: spec.y, series: spec.series, title: spec.title, columns: spec.columns },
      sql: spec.sql ?? "",
    });
    setPinned(true);
  }
  return (
    <div className="chart-card">
      <div className="head">
        <h4>{spec.title ?? "Chart"}</h4>
        <button className="btn ghost small" onClick={pin} disabled={pinned || !spec.sql}>
          {pinned ? "Pinned ✓" : "Pin to dashboard"}
        </button>
      </div>
      <ChartView spec={spec} />
    </div>
  );
}
