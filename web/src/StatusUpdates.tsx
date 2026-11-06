import React, { useCallback, useEffect, useRef, useState } from "react";

type Update = { id: number; text: string; kind: "info" | "error"; time: string };
export function useStatusUpdates() {
  const sequence = useRef(0);
  const [state, setState] = useState<{ current?: Update; history: Update[] }>({ history: [] });
  const publish = useCallback((text: string, kind: Update["kind"]) => {
    if (!text) return;
    const update = { id: ++sequence.current, text, kind, time: new Date().toISOString() };
    setState(old => ({ current: update, history: [update, ...old.history].slice(0, 50) }));
  }, []);
  const info = useCallback((text: string) => publish(text, "info"), [publish]);
  const error = useCallback((text: string) => publish(text, "error"), [publish]);
  const reset = useCallback(() => setState({ history: [] }), []);
  const dismiss = useCallback((id: number) => setState(old => ({
    current: old.current?.id === id ? undefined : old.current,
    history: old.history.filter(update => update.id !== id),
  })), []);
  useEffect(() => {
    if (!state.current) return;
    const id = state.current.id;
    const timer = setTimeout(() => setState(old => old.current?.id === id
      ? { ...old, current: undefined } : old), state.current.kind === "error" ? 12000 : 8000);
    return () => clearTimeout(timer);
  }, [state.current]);
  return { ...state, info, error, reset, dismiss };
}

export function StatusUpdates({ current, history, onDismiss }: { current?: Update; history: Update[]; onDismiss: (id: number) => void }) {
  const [expanded, setExpanded] = useState(false);
  useEffect(() => { if (!history.length) setExpanded(false); }, [history.length]);
  return <section className="status-updates" aria-label="Updates">
    {expanded && <div className="update-history" id="update-history">
      <div className="update-history-heading">
        <h2>Recent updates</h2>
        <button onClick={() => setExpanded(false)} aria-label="Close update history">Close</button>
      </div>
      <ol>
        {history.map(update => <li key={update.id} className={update.kind === "error" ? "update-error" : undefined}>
          <time dateTime={update.time}>{new Date(update.time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
          <span>{update.kind === "error" && "Error: "}{update.text}</span>
          <button aria-label={`Dismiss update: ${update.text}`} onClick={() => onDismiss(update.id)}>×</button>
        </li>)}
      </ol>
    </div>}
    <div className="update-line">
      <p key={current?.id ?? "empty"} role={current?.kind === "error" ? "alert" : "status"}
        className={current?.kind === "error" ? "update-error" : undefined} title={current?.text}>
        {current?.text || "Ready."}
      </p>
      {current && <button aria-label="Dismiss current update" onClick={() => onDismiss(current.id)}>×</button>}
      <button aria-expanded={expanded} aria-controls="update-history" disabled={!history.length}
        onClick={() => setExpanded(old => !old)}>
        Updates ({history.length}) <span aria-hidden="true">{expanded ? "▾" : "▴"}</span>
      </button>
    </div>
  </section>;
}
