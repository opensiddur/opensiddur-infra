import { useEffect, useRef, useState } from "react";
import { api, download, deletionStatus, needsEmail, finishEmail, reauthenticateGoogle, emailReauthentication, type User, type Value } from "./api";

export function AccountDataControls({ user, preferences, onDeleting, onDeleted }: {
  user: User | null; preferences: Value; onDeleting: (active: boolean) => void; onDeleted: () => Promise<void>;
}) {
  const [operation, setOperation] = useState<Value>(() => {
    const id = sessionStorage.getItem("account-export");
    return id ? { id, state: "queued", phase: "Checking download" } : undefined;
  });
  const [receipt, setReceipt] = useState(() => sessionStorage.getItem("account-deletion-receipt"));
  const [phase, setPhase] = useState("Removing your account and data…");
  const [dialog, setDialog] = useState(() => sessionStorage.getItem("account-delete-pending") === "true" && !needsEmail());
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reauth, setReauth] = useState(false);
  const [done, setDone] = useState(false);
  const [emailReturn, setEmailReturn] = useState(() => needsEmail());
  const modal = useRef<HTMLDialogElement>(null);
  const complete = useRef(onDeleted); complete.current = onDeleted;
  useEffect(() => { if (user) setDone(false); }, [user?.uid]);
  useEffect(() => {
    const resumed = () => {
      if (sessionStorage.getItem("account-delete-pending")) {
        setEmailReturn(false); setReauth(false); setConfirmation(""); setDialog(true);
      }
    };
    window.addEventListener("account-reauthenticated", resumed);
    return () => window.removeEventListener("account-reauthenticated", resumed);
  }, []);
  useEffect(() => {
    const element = modal.current;
    if (!element) return;
    if (dialog && !receipt) { if (!element.open) element.showModal(); }
    else if (element.open) element.close();
  }, [dialog, receipt, user?.uid, done]);
  useEffect(() => {
    if (!operation?.id || !user || receipt || ["succeeded", "failed"].includes(operation.state)) return;
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const row = await api("/account/exports/" + operation.id);
        if (!active) return;
        setOperation(row);
        if (["succeeded", "failed"].includes(row.state)) sessionStorage.removeItem("account-export");
        else timer = setTimeout(poll, 2000);
      } catch (cause) {
        if (active && [404, 410].includes((cause as { status: number }).status)) {
          sessionStorage.removeItem("account-export");
          setOperation({ id: operation.id, state: "failed", phase: "Download expired or is unavailable; prepare a new download." });
        } else if (active) { setError(String(cause)); timer = setTimeout(poll, 5000); }
      }
    };
    poll();
    return () => { active = false; clearTimeout(timer); };
  }, [operation?.id, user?.uid, receipt]);
  useEffect(() => {
    if (!receipt) return;
    let active = true; let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const row = await deletionStatus(receipt);
        if (!active) return;
        setPhase(row.phase); setError("");
        if (row.state === "succeeded") {
          for (const storage of [localStorage, sessionStorage]) {
            for (const key of Object.keys(storage)) {
              if (key.startsWith("builder-") || key.startsWith("account-") || key === "loginEmail") storage.removeItem(key);
            }
          }
          await complete.current();
          if (active) { setReceipt(null); setDone(true); }
        } else timer = setTimeout(poll, 2000);
      } catch (cause) {
        if (active && (cause as { status?: number }).status === 404) {
          sessionStorage.removeItem("account-deletion-receipt"); setReceipt(null);
          onDeleting(false); setDialog(true); setConfirmation("");
          setError("Deletion status is unavailable or has expired. Sign in to check your account before confirming again.");
        } else if (active) { setError("Could not check deletion progress. Cleanup continues; retrying automatically."); timer = setTimeout(poll, 5000); }
      }
    };
    poll();
    return () => { active = false; clearTimeout(timer); };
  }, [receipt]);
  async function exportData() {
    setBusy(true); setError("");
    try {
      const row = await api("/account/export", "POST", { browser_preferences: preferences });
      sessionStorage.setItem("account-export", row.id); setOperation(row);
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  function cancel() {
    setDialog(false); setConfirmation(""); setReauth(false);
    sessionStorage.removeItem("account-delete-pending");
  }
  async function erase() {
    setBusy(true); setError("");
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    const token = Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");
    sessionStorage.setItem("account-deletion-receipt", token);
    try {
      await api("/account", "DELETE", { confirmation, receipt: token });
      sessionStorage.setItem("account-deletion-receipt", token);
      setReceipt(token); setDialog(false); onDeleting(true);
    } catch (cause) {
      // Resolve a lost HTTP response before allowing a second deletion attempt.
      try {
        await deletionStatus(token);
        sessionStorage.setItem("account-deletion-receipt", token);
        setReceipt(token); setDialog(false); onDeleting(true);
      } catch (statusError) {
        if (!(statusError as { status?: number }).status && !(cause as { status?: number }).status) {
          // Both responses were lost. Keep the receipt across reloads until status resolves.
          setReceipt(token); setDialog(false); onDeleting(true); return;
        }
        sessionStorage.removeItem("account-deletion-receipt");
        setError(String(cause));
        if ((cause as { status?: number }).status === 401) {
          setReauth(true); setConfirmation("");
          sessionStorage.setItem("account-delete-pending", "true");
        }
      }
    } finally { setBusy(false); }
  }
  async function googleAgain() {
    setBusy(true); setError("");
    try { await reauthenticateGoogle(); setReauth(false); setConfirmation(""); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function emailAgain() {
    setBusy(true); setError("");
    try { await emailReauthentication(); setError("Check your email, open the link in this browser, then confirm deletion again."); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  if (done) return <p role="status">Your account and data have been deleted.</p>;
  if (receipt) return <section aria-label="Account deletion"><p role="status">{phase}</p>{error && <p role="alert">{error}</p>}</section>;
  if (!user) return null;
  const exporting = operation && !["succeeded", "failed"].includes(operation.state);
  return <section aria-label="Your data" className="account-data-controls">
    <h2>Your data</h2>
    {emailReturn && sessionStorage.getItem("account-delete-pending") && <button onClick={async () => {
      try { await finishEmail(user.email || ""); setEmailReturn(false); setReauth(false); setConfirmation(""); setDialog(true); }
      catch (cause) { setError(String(cause)); }
    }}>Finish signing in to confirm deletion</button>}
    <button disabled={busy || exporting} onClick={exportData}>Download all my data</button>
    {operation && <p role="status">{operation.phase}</p>}
    {operation?.state === "succeeded" && <button onClick={async () => {
      try { await download(`/account/exports/${operation.id}/download`, "account-data.zip"); }
      catch (cause) { setError(String(cause)); }
    }}>Download ZIP</button>}
    <p className="hint">Includes retained records, files, and this browser’s preferences. Active builds may change after preparation starts. Downloads expire after 24 hours.</p>
    <button className="danger" onClick={() => { setDialog(true); setConfirmation(""); setError(""); }}>Delete my account</button>
    {error && <p role="alert">{error}</p>}
    <dialog ref={modal} aria-labelledby="delete-account-title" onCancel={e => { e.preventDefault(); if (!busy) cancel(); }}>
      <h2 id="delete-account-title">Delete my account</h2>
      <p>This permanently removes your account, saved preferences, builds, uploaded files, and Firebase sign-in account. Access stops immediately; cleanup progress appears here.</p>
      <p>Provider-required audit records follow provider retention rules. Recovery copies we control are kept for at most 30 days. Copies already downloaded by others cannot be recalled.</p>
      <button disabled={busy || exporting} onClick={exportData}>Download all my data</button>
      {operation && <p role="status">{operation.phase}</p>}
      {operation?.state === "succeeded" && <button onClick={async () => {
        try { await download(`/account/exports/${operation.id}/download`, "account-data.zip"); }
        catch (cause) { setError(String(cause)); }
      }}>Download ZIP</button>}
      {error && <p role="alert">{error}</p>}
      {reauth ? <div>
        <p>Sign in again to continue, then type DELETE again.</p>
        {user.providerData?.some(p => p.providerId === "google.com") && <button disabled={busy} onClick={googleAgain}>Sign in again with Google</button>}
        {user.email && <button disabled={busy} onClick={emailAgain}>Email me a confirmation sign-in link</button>}
      </div> : <label>Type DELETE to confirm
        <input autoComplete="off" value={confirmation} onChange={e => setConfirmation(e.target.value)} />
      </label>}
      <button disabled={busy} onClick={cancel}>Cancel</button>
      <button className="danger" disabled={busy || reauth || confirmation !== "DELETE"} onClick={erase}>Permanently delete my account</button>
    </dialog>
  </section>;
}
