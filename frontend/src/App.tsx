import { useState } from "react";
import { Chat } from "./components/Chat";
import { Dashboard } from "./components/Dashboard";
import { Explore } from "./components/Explore";

type Tab = "chat" | "explore" | "dashboard";

const TABS: { id: Tab; label: string }[] = [
  { id: "chat", label: "Chat" },
  { id: "explore", label: "Explore" },
  { id: "dashboard", label: "Dashboard" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("chat");

  return (
    <>
      <nav className="nav">
        <div className="brand">
          <span className="diamond" />
          Exaqube <em>analytics</em>
        </div>
        <div className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab-btn ${tab === t.id ? "active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      <div className="page">
        <h1 className="section-title">
          {tab === "chat" && <>Ask the <em>data</em></>}
          {tab === "explore" && <>Explore the <em>servers</em></>}
          {tab === "dashboard" && <>Pinned <em>dashboard</em></>}
        </h1>
        <p className="subtle" style={{ marginTop: 0, marginBottom: 20 }}>
          {tab === "chat" && "The agent writes SQL, runs it read-only, and can build charts and workbooks."}
          {tab === "explore" && "Browse servers, members, and activity straight from the API."}
          {tab === "dashboard" && "Charts you pin here persist and re-run their query on load."}
        </p>

        {tab === "chat" && <Chat />}
        {tab === "explore" && <Explore />}
        {tab === "dashboard" && <Dashboard />}
      </div>
    </>
  );
}
