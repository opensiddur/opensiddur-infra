import React, { useCallback, useEffect, useRef, useState } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { parse, stringify } from "yaml";
import {
  api,
  auth,
  google,
  emailLink,
  finishEmail,
  needsEmail,
  logout,
  download,
  runtime,
  type User,
  type Value,
} from "./api";
import { SchemaField, Sources, Declarations } from "./Settings";
import { normalizeSettings } from "./settings-data";
import { Allowance, PublishedPresets, SettingHelp, projectLabel } from "./BuilderControls";
import { SearchSelect } from "./SearchSelect";
import { LicenseNotice } from "./LicenseNotice";
import { BuildProgress } from "./BuildProgress";
import { RequiredMark } from "./RequiredMark";
import { PresetNameForm } from "./PresetNameForm";
import { SettingsEditContext } from "./SchemaField";
import { TypographyMetadata, runningHeadIssues } from "./TypographyControls";
import { StatusUpdates, useStatusUpdates } from "./StatusUpdates";
import "./style.css";
const terminal = new Set([
  "succeeded",
  "partial",
  "failed",
  "cancelled",
  "expired",
]);
function buildStatus(state: string): string {
  return ({ queued: "Queued", running: "Running", succeeded: "Complete",
    partial: "Complete with errors", failed: "Failed", cancelled: "Cancelled", expired: "Expired" } as Record<string, string>)[state] || state;
}
function SampleAllowance({ allowances }: { allowances?: Value }) {
  const counts = allowances?.samples;
  return counts ? <p className="hint">
    Samples today: {counts.html.used} of {counts.html.limit} text; {counts.pdf.used} of {counts.pdf.limit} print.
  </p> : null;
}
export function App() {
  const [catalog, setCatalog] = useState<Value>(),
    [schema, setSchema] = useState<Value>(),
    [settings, setSettingsState] = useState<Value>({}),
    [user, setUser] = useState<User | null>(null),
    [account, setAccount] = useState<Value>(),
    [email, setEmail] = useState(sessionStorage.getItem("loginEmail") || ""),
    [tab, setTab] = useState("Sources"),
    [advanced, setAdvanced] = useState(
      () => localStorage.getItem("builder-advanced") === "true",
    ),
    [publishedPreset, setPublishedPreset] = useState(""),
    [formats, setFormats] = useState(["pdf", "html"]),
    [history, setHistory] = useState<Value[]>([]),
    [presets, setPresets] = useState<Value[]>([]),
    [preview, setPreview] = useState(""),
    [previewMode, setPreviewMode] = useState<"html" | "pdf">("html"),
    [previewRevision, refreshPreview] = useState(0),
    [previewStatus, setPreviewStatus] = useState("Sign in to see a sample"),
    [yaml, setYaml] = useState(""),
    [route, setRoute] = useState(() => location.pathname + location.hash),
    [asset, setAsset] = useState<string | null>(null),
    [notice, setNotice] = useState<Value>(),
    [share, setShare] = useState<Value>();
  const updates = useStatusUpdates();
  const setMessage = updates.info, setError = updates.error;
  const [currentBuild, setCurrentBuild] = useState<Value>();
  const [buildError, setBuildError] = useState("");
  const [building, setBuilding] = useState(false);
  const [loadedPreset, setLoadedPreset] = useState("");
  const [settingsEpoch, setSettingsEpoch] = useState(0);
  const [loadingSettings, setLoadingSettings] = useState(false);
  const [savingPreset, setSavingPreset] = useState(false);
  const [renamingPreset, setRenamingPreset] = useState<string | null>(null);
  const [pendingFields, setPendingFields] = useState<Set<string>>(new Set());
  const headerIssues = runningHeadIssues(settings.typography, catalog?.running_head_codes);
  const hasPendingSettings = pendingFields.size > 0 || headerIssues.length > 0;
  const reportPending = useCallback(
    (id: string, pending: boolean) =>
      setPendingFields((old) => {
        if (old.has(id) === pending) return old;
        const next = new Set(old);
        if (pending) next.add(id);
        else next.delete(id);
        return next;
      }),
    [],
  );
  const hasConsent =
    !!account?.consent && account.consent.version === account.consent_version;
  const generation = useRef(0),
    pendingPreview = useRef<string | null>(null);
  const path = route.split("#")[0];
  const accountOpen =
    route.endsWith("#account") ||
    path === "/account" ||
    path === "/login" ||
    needsEmail();
  function navigate(destination: string) {
    window.history.pushState({}, "", destination);
    setRoute(location.pathname + location.hash);
  }
  function openAccount(e?: React.MouseEvent) {
    e?.preventDefault();
    if (!needsEmail()) navigate("/#account");
  }
  useEffect(() => {
    const changed = () => setRoute(location.pathname + location.hash);
    addEventListener("popstate", changed);
    addEventListener("hashchange", changed);
    return () => {
      removeEventListener("popstate", changed);
      removeEventListener("hashchange", changed);
    };
  }, []);
  useEffect(() => {
    if (!user || !path.startsWith("/builds/")) return;
    const id = path.slice("/builds/".length);
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    setBuildError("");
    async function poll() {
      try {
        const row = await api("/builds/" + encodeURIComponent(id));
        if (!active) return;
        setCurrentBuild(row);
        if (!terminal.has(row.state)) timer = setTimeout(poll, 2000);
      } catch (cause) {
        if (active) setBuildError(cause instanceof Error ? cause.message : "Build unavailable");
      }
    }
    poll();
    return () => { active = false; clearTimeout(timer); };
  }, [path, user?.uid]);
  function setSettings(value: Value | ((old: Value) => Value)) {
    setLoadedPreset("");
    if (typeof value === "function")
      setSettingsState((old: Value) => normalizeSettings(value(old)));
    else setSettingsState(normalizeSettings(value));
  }
  useEffect(() => {
    localStorage.setItem("builder-advanced", String(advanced));
  }, [advanced]);
  function changeAdvanced(enabled: boolean) {
    setAdvanced(enabled);
    if (!enabled && tab === "Advanced") setTab("Sources");
  }
  function fail(e: unknown) {
    setError(e instanceof Error ? e.message : String(e));
  }
  async function action(fn: () => Promise<unknown>) {
    try {
      await fn();
    } catch (e) {
      fail(e);
    }
  }
  useEffect(() => {
    if (auth) return onAuthStateChanged(auth, setUser);
  }, []);
  useEffect(() => {
    api("/catalog").then(setCatalog).catch(fail);
    api("/schema").then(setSchema).catch(fail);
  }, []);
  useEffect(() => {
    if (path === "/licenses") api("/notices").then(setNotice).catch(fail);
    if (path.startsWith("/share/"))
      api("/shares/" + path.split("/")[2])
        .then(setShare)
        .catch(fail);
  }, [path]);
  useEffect(() => {
    if (user)
      action(async () => {
        setAccount(await api("/account"));
        setPresets(await api("/presets"));
        setHistory(await api("/builds"));
      });
    else {
      setCurrentBuild(undefined);
      setSavingPreset(false);
      setRenamingPreset(null);
      setAccount(undefined);
      setHistory([]);
      setPresets([]);
      setPreview("");
      setPreviewStatus("Sign in to see a sample");
      setSettings({});
      setAsset(null);
      updates.reset();
    }
  }, [user]);
  useEffect(() => {
    setYaml(stringify(settings));
  }, [settings]);
  useEffect(() => {
    if (!user) return;
    let active = true;
    const timer = setInterval(() => {
      Promise.all([api("/builds"), api("/account")])
        .then(([rows, current]) => {
          if (active) {
            setHistory(rows);
            setAccount(current);
          }
        })
        .catch((e) => {
          if (active) fail(e);
        });
    }, 10000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [user]);
  useEffect(() => {
    return () => { if (preview.startsWith("blob:")) URL.revokeObjectURL(preview); };
  }, [preview]);
  const signature = JSON.stringify({ settings, asset });
  useEffect(() => {
    const revision = ++generation.current;
    setPreview("");
    if (!user || !hasConsent || !settings.book || hasPendingSettings) return;
    if (previewMode === "pdf" && account?.allowances?.pdf_samples_remaining === 0) {
      setPreviewStatus("No print samples remaining today. Switch to text preview to continue previewing.");
      return;
    }
    const timer = setTimeout(
      () =>
        action(async () => {
          if (pendingPreview.current) {
            const previous = pendingPreview.current;
            await api("/builds/" + previous + "/cancel", "POST").catch(
              () => {},
            );
            for (let n = 0; n < 20; n++) {
              const old = await api("/builds/" + previous).catch(() => null);
              if (!old || terminal.has(old.state)) break;
              await new Promise((r) => setTimeout(r, 500));
            }
          }
          if (generation.current !== revision) return;
          setPreviewStatus(previewMode === "pdf" ? "Typesetting print sample…" : "Preparing text sample…");
          const build = await api("/builds", "POST", {
            release: catalog.release,
            settings,
            formats: [previewMode],
            type: previewMode,
            asset,
            idempotency_key: crypto.randomUUID(),
          });
          pendingPreview.current = build.id;
          if (generation.current !== revision) {
            await api("/builds/" + build.id + "/cancel", "POST");
            return;
          }
          for (let i = 0; i < (previewMode === "pdf" ? 300 : 90); i++) {
            await new Promise((r) => setTimeout(r, 1000));
            if (generation.current !== revision) return;
            const state = await api("/builds/" + build.id);
            if (terminal.has(state.state)) {
              pendingPreview.current = null;
              if (state.state === "succeeded") {
                const token = await user.getIdToken();
                const response = await fetch(
                  "/api/v1/builds/" + build.id + "/preview",
                  { headers: { Authorization: "Bearer " + token } },
                );
                if (!response.ok) throw new Error("Sample unavailable");
                const content = previewMode === "pdf"
                  ? URL.createObjectURL(await response.blob())
                  : await response.text();
                if (generation.current === revision) {
                  setPreview(content);
                  setPreviewStatus(previewMode === "pdf" ? "Print sample updated" : "Text sample updated");
                } else if (previewMode === "pdf") URL.revokeObjectURL(content);
              } else
                setPreviewStatus(
                  "Sample unavailable: " + JSON.stringify(state.results),
                );
              return;
            }
          }
          setPreviewStatus(
            "Sample is taking longer than expected; see build history.",
          );
        }),
      previewMode === "pdf" ? 1500 : 750,
    );
    return () => clearTimeout(timer);
  }, [signature, previewMode, previewRevision, user?.uid, hasConsent, hasPendingSettings]);
  async function prepareSettings(value: Value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
      throw new Error("Settings must be a mapping");
    const normalized = normalizeSettings(value);
    return user && hasConsent
      ? (await api("/validate", "POST", normalized)).settings
      : normalized;
  }
  function replaceSettings(value: Value) {
    setSettings(value);
    setPublishedPreset("");
    setPendingFields(new Set());
    setSettingsEpoch((old) => old + 1);
    setSavingPreset(false);
  }
  async function applySettings(value: Value) {
    const next = await prepareSettings(value);
    replaceSettings(next);
    setAsset(null);
    setMessage(user && hasConsent
      ? "Settings loaded."
      : "Settings loaded locally. Full validation runs after sign-in and consent.");
  }
  async function loadPreset(preset: Value) {
    setLoadingSettings(true);
    try {
      const next = await prepareSettings(preset.settings);
      replaceSettings(next);
      setAsset(preset.asset || null);
      changeAdvanced(preset.preferences?.advanced === true);
      setFormats(preset.preferences?.formats || ["pdf", "html"]);
      setLoadedPreset(preset.id);
      setTab("Sources");
      setMessage(`Loaded ${preset.name}.`);
      navigate("/");
    } finally { setLoadingSettings(false); }
  }
  async function importSettings(file: File) {
    setLoadingSettings(true);
    try {
      if (file.size > 262144) throw new Error("Choose a settings YAML file smaller than 256 KiB.");
      await applySettings(parse(await file.text()));
      setTab("Sources");
    } finally { setLoadingSettings(false); }
  }
  function setRoot(key: string, value: Value) {
    setSettings((old: Value) => {
      const next = { ...old };
      if (value === undefined) delete next[key];
      else next[key] = value;
      return next;
    });
  }
  function choose(id: string) {
    const project = catalog.projects.find((p: Value) => p.id === id);
    if (!project) {
      replaceSettings({});
      setPublishedPreset("");
      setAsset(null);
      return;
    }
    const preset = project.presets?.[0];
    const next = preset?.settings || { book: { project: id, file_name: "index.xml" } };
    const transclusion = next.priority?.transclusion ?? [];
    replaceSettings(
      transclusion.includes(id)
        ? next
        : { ...next, priority: { ...next.priority, transclusion: [...transclusion, id] } },
    );
    setPublishedPreset(preset ? "0" : "");
    setAsset(null);
  }
  async function build() {
    if (building) return;
    setBuilding(true);
    try {
      const row = await api("/builds", "POST", {
        release: catalog.release, settings,
        formats: formats.filter((f) => advanced || ["pdf", "html"].includes(f)),
        type: "full", asset, idempotency_key: crypto.randomUUID(),
      });
      setHistory((old) => [row, ...old]);
      setCurrentBuild(row);
      navigate("/builds/" + row.id);
      setAccount(await api("/account"));
    } finally {
      setBuilding(false);
    }
  }
  async function save(name: string, existingId?: string) {
    const id = existingId || crypto.randomUUID();
    await api("/presets/" + id, "PUT", {
      name,
      settings,
      asset,
      preferences: { advanced, formats },
    });
    setPresets(await api("/presets"));
    setSavingPreset(false);
    setLoadedPreset(id);
    setMessage("Preset saved until you delete it.");
  }
  function localFile(name: string, data: string) {
    const link = document.createElement("a");
    const url = URL.createObjectURL(new Blob([data]));
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const previewBlocker = headerIssues[0] || (loadingSettings ? "Wait for settings to finish loading."
    : !settings.book ? "Choose a starting text or load settings first."
    : hasPendingSettings ? "Complete or cancel unfinished settings first."
    : "");
  const buildBlocker = previewBlocker || (!formats.some((format) => advanced || ["pdf", "html"].includes(format))
      ? "Select at least one output format before building." : "");
  const fullHistory = history.filter((row) => row.type === "full").sort((a, b) =>
    (Number(b.created) || 0) - (Number(a.created) || 0) || String(b.id).localeCompare(String(a.id)));
  const projects = catalog?.projects || [],
    selected = projects.find((p: Value) => p.id === settings.book?.project);
  const guided =
    tab === "Customs"
      ? ["readings", "print_once", "electronic"]
      : tab === "Typography"
        ? ["typography"]
        : tab === "Distribution"
          ? ["distribution"]
          : [];
  const accountPanel = (
    <section className="card" id="account">
      <p className="eyebrow">YOUR ACCOUNT</p>
      {!user ? (
        <>
          <p>
            Browse and edit freely. Sign in to preview, build, or save settings.
          </p>
          {runtime.googleEnabled && (
            <button onClick={() => action(google)}>Continue with Google</button>
          )}
          <label>
            Email address<RequiredMark />
            <input
              type="email"
              required aria-required="true"
              aria-invalid={!email.trim() || undefined}
              className={!email.trim() ? "required-empty" : undefined}
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <button
            disabled={!auth || !email}
            onClick={() =>
              action(async () => {
                if (needsEmail()) await finishEmail(email);
                else {
                  await emailLink(email);
                  setMessage("Check your email for a sign-in link.");
                }
              })
            }
          >
            {needsEmail() ? "Finish signing in" : "Email me a sign-in link"}
          </button>
        </>
      ) : (
        <>
          <p>Signed in as {user.email}</p>
          {!account ? (
            <p role="status">Loading account…</p>
          ) : !hasConsent ? (
            <>
              <p>
                Your settings and generated books may reveal religious beliefs.
                We process them to generate your books. Artifacts and build
                history expire after 30 days; presets are saved only when you
                ask, until deleted. You can withdraw consent and delete your
                data.
              </p>
              <a href="/privacy">Privacy notice</a>
              <button
                onClick={() =>
                  action(async () => {
                    await api("/consent", "POST", {
                      version: account.consent_version,
                    });
                    setAccount(await api("/account"));
                  })
                }
              >
                I explicitly consent to this processing
              </button>
            </>
          ) : (
            <p>
              Hosted processing consent recorded. You can withdraw it below.
            </p>
          )}
          {runtime.googleEnabled && (
            <button onClick={() => action(google)}>
              Link a Google sign-in
            </button>
          )}
          <details>
            <summary>Saved presets & account controls</summary>
            {presets.map((p) => (
              <div className="row" key={p.id}>
                <button
                  onClick={() => action(() => loadPreset(p))}
                  disabled={loadingSettings}
                >
                  {p.name}
                </button>
                {renamingPreset === p.id ? (
                  <PresetNameForm initialName={p.name}
                    onCancel={() => setRenamingPreset(null)}
                    onSave={async (name) => {
                      await api("/presets/" + p.id, "PUT", { ...p, name });
                      setPresets(await api("/presets"));
                      setRenamingPreset(null);
                    }} />
                ) : (
                  <button onClick={() => setRenamingPreset(p.id)}>Rename</button>
                )}
                <button
                  onClick={() =>
                    action(async () => {
                      await api("/presets/" + p.id, "DELETE");
                      setPresets(await api("/presets"));
                    })
                  }
                >
                  Delete preset
                </button>
              </div>
            ))}
            <button
              onClick={() =>
                action(async () =>
                  localFile(
                    "account-export.json",
                    JSON.stringify(await api("/account/export"), null, 2),
                  ),
                )
              }
            >
              Export my data
            </button>
            <button
              onClick={() =>
                action(async () => {
                  if (
                    confirm(
                      "Withdraw consent and delete hosted settings and builds?",
                    )
                  ) {
                    await api("/consent", "DELETE");
                    setAccount(await api("/account"));
                    setPresets([]);
                    setHistory([]);
                  }
                })
              }
            >
              Withdraw consent
            </button>
            <button
              className="danger"
              onClick={() =>
                action(async () => {
                  if (
                    confirm(
                      "Delete your account, saved presets and generated files?",
                    )
                  ) {
                    await api("/account", "DELETE");
                    await logout();
                  }
                })
              }
            >
              Delete account
            </button>
          </details>
        </>
      )}
    </section>
  );
  function renderLogs(b: Value) {
    const logs = (b.artifacts || []).filter((artifact: Value) => /\.(log|blg)$/.test(artifact.name));
    return logs.length > 0 ? <section className="build-logs">
      <h3>Logs</h3>
      <p className="hint">Private logs follow this build’s expiry and are excluded from share links.</p>
      <div className="row wrap">{logs.map((artifact: Value) => <button key={artifact.name}
        onClick={() => action(() => download("/builds/" + b.id + "/files/" + encodeURIComponent(artifact.name), artifact.name))}>
        Download {artifact.name}
      </button>)}</div>
    </section> : <section className="build-logs"><h3>Logs</h3><p className="hint">{terminal.has(b.state)
      ? "No downloadable logs were retained for this build."
      : "Logs will appear here as the build runs."}</p></section>;
  }
  function renderBuild(b: Value, compact = false) {
    if (compact) return (
      <article className="card" key={b.id}>
        <div className="row wrap">
          <strong>{b.title || "Untitled work"} · {buildStatus(b.state)}</strong>
          {b.created && <time dateTime={new Date(b.created * 1000).toISOString()}>{new Date(b.created * 1000).toLocaleString()}</time>}
          <a href={"/builds/" + b.id} onClick={(event) => {
            event.preventDefault(); navigate("/builds/" + b.id);
          }}>View build</a>
        </div>
        {!terminal.has(b.state) && <p>{b.stage || "Waiting to start"}</p>}
        {(!terminal.has(b.state) || b.artifacts?.some((a: Value) => /\.(log|blg)$/.test(a.name))) &&
          <BuildProgress build={b} showSteps={!terminal.has(b.state)}>{renderLogs(b)}</BuildProgress>}
      </article>
    );
    return (
      <article className="card" key={b.id}>
                    <div className="row">
                      <strong>
                        {b.title || "Untitled work"} · {buildStatus(b.state)}
                      </strong>
                      <code>{b.id}</code>
                      {path !== "/builds/" + b.id && <a href={"/builds/" + b.id} onClick={(e) => {
                        e.preventDefault(); navigate("/builds/" + b.id);
                      }}>View build</a>}
                    </div>
                    <p>
                      {b.stage}{" "}
                      {b.expires &&
                        "· Expires " +
                          new Date(b.expires * 1000).toLocaleDateString()}
                    </p>
                    {Object.entries(b.results || {}).map(([f, r]) => (
                      <p key={f}>
                        {f}: {(r as Value).state} {(r as Value).message}
                      </p>
                    ))}
                    <div className="row wrap">
                      {b.artifacts.filter((a: Value) => !/\.(log|blg)$/.test(a.name)).map((a: Value) => (
                        <button
                          key={a.name}
                          onClick={() =>
                            action(() =>
                              download(
                                "/builds/" +
                                  b.id +
                                  "/files/" +
                                  encodeURIComponent(a.name),
                                a.name,
                              ),
                            )
                          }
                        >
                          {a.name}
                        </button>
                      ))}
                      {!terminal.has(b.state) && (
                        <button
                          onClick={() =>
                            action(() =>
                              api("/builds/" + b.id + "/cancel", "POST"),
                            )
                          }
                        >
                          Cancel
                        </button>
                      )}
                      {b.type === "full" &&
                        ["succeeded", "partial"].includes(b.state) && (
                          <>
                            <button
                              onClick={() =>
                                action(async () => {
                                  const { token } = await api(
                                    "/builds/" + b.id + "/share",
                                    "POST",
                                    { enabled: true },
                                  );
                                  setMessage(
                                    "Share link (anyone with it can download PDF/HTML until expiry): " +
                                      location.origin +
                                      "/share/" +
                                      token,
                                  );
                                })
                              }
                            >
                              Create share link
                            </button>
                            <button
                              onClick={() =>
                                action(() =>
                                  api("/builds/" + b.id + "/share", "POST", {
                                    enabled: false,
                                  }),
                                )
                              }
                            >
                              Revoke sharing
                            </button>
                          </>
                        )}
                      <button
                        className="danger"
                        onClick={() =>
                          action(async () => {
                            await api("/builds/" + b.id, "DELETE");
                            setHistory(await api("/builds"));
                            if (path === "/builds/" + b.id) navigate("/builds");
                          })
                        }
                      >
                        Delete
                      </button>
                    </div>
                    <BuildProgress build={b}>{renderLogs(b)}</BuildProgress>
                  </article>
    );
  }
  return (
    <TypographyMetadata.Provider value={{
      fonts: catalog?.font_catalog,
      codes: catalog?.running_head_codes,
      customFontFamilies: Object.keys(settings.typography?.fonts || {}),
    }}>
    <SettingsEditContext.Provider value={reportPending}>
      <header>
        <div className="brand-row">
          <a href="https://opensiddur.org/" className="brand">
            <img
              src="/opensiddur-logo.svg"
              alt="The Open Siddur Project logo"
              width="76"
              height="76"
            />
            <span>
              the Open Siddur Project{" "}
              <span lang="he" dir="rtl">
                פְּרוֹיֶקְט הַסִּדּוּר הַפָּתוּחַ
              </span>
            </span>
          </a>
          <details
            className="account-menu"
            onBlur={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget))
                e.currentTarget.removeAttribute("open");
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.currentTarget.removeAttribute("open");
                e.currentTarget.querySelector("summary")?.focus();
              }
            }}
          >
            <summary>Account</summary>
            <div className="account-menu-panel">
              {user && <p className="account-menu-name">{user.displayName || user.email || "Signed in"}</p>}
              <a
                href="/#account"
                onClick={(e) => {
                  openAccount(e);
                  e.currentTarget.closest("details")?.removeAttribute("open");
                }}
              >
                {user ? "Account & saved presets" : "Sign in"}
              </a>
              {user && (
                <button
                  onClick={(e) => {
                    e.currentTarget.closest("details")?.removeAttribute("open");
                    action(async () => {
                      await logout();
                      navigate("/#account");
                    });
                  }}
                >
                  Sign out
                </button>
              )}
            </div>
          </details>
        </div>
        <nav>
          <a
            href="/"
            onClick={(e) => {
              e.preventDefault();
              navigate("/");
            }}
          >
            Builder
          </a>
          <a
            href="/builds"
            aria-current={path.startsWith("/builds") && !accountOpen ? "page" : undefined}
            onClick={(e) => {
              e.preventDefault();
              navigate("/builds");
            }}
          >
            Build history
          </a>
          <a
            href="/licenses"
            onClick={(e) => {
              e.preventDefault();
              navigate("/licenses");
            }}
          >
            Software licenses
          </a>
        </nav>
      </header>
      {accountOpen ? (
        <main className="account-page">
          <h1>{user ? "Your account" : "Sign in"}</h1>
          <p>
            <a
              href="/"
              onClick={(e) => {
                e.preventDefault();
                navigate("/");
              }}
            >
              ← Return to the builder
            </a>
          </p>
          {accountPanel}
        </main>
      ) : path.startsWith("/builds/") ? (
        <main className="history-page">
          <h1>Build status</h1>
          <p><a href="/builds" onClick={(e) => { e.preventDefault(); navigate("/builds"); }}>All builds</a></p>
          {!user ? <p><a href="/#account" onClick={openAccount}>Sign in to see this build.</a></p>
            : buildError ? <p role="alert">{buildError}</p>
            : currentBuild?.id === path.slice("/builds/".length) ? <>
              <p role="status">{buildStatus(currentBuild.state)}: {currentBuild.stage || "Waiting to start"}</p>
              <p>You can leave this page and return later from Build history. Downloads appear here when ready.</p>
              {renderBuild(currentBuild)}
            </> : <p role="status">Loading build…</p>}
        </main>
      ) : path === "/builds" ? (
        <main className="history-page">
          <h1>Build history</h1>
          <SampleAllowance allowances={account?.allowances} />
          {user ? (
            <section className="history">
              <h2>Your builds</h2>
              {fullHistory.length === 0 ? (
                <p>No builds yet.</p>
              ) : (
                fullHistory.map((b) => renderBuild(b, true))
              )}
            </section>
          ) : (
            <p><a href="/#account" onClick={openAccount}>Sign in to see your builds.</a></p>
          )}
        </main>
      ) : path === "/licenses" ? (
        <main>
          <p className="eyebrow">OPEN SOURCE</p>
          <h1>Software licenses & notices</h1>
          <p>
            These notices describe the deployed software. Liturgical texts have
            separate licenses recorded in their TEI headers and in each
            generated book’s colophon.
          </p>
          <p>
            Application: LGPL-3.0-or-later ·{" "}
            <a href="https://github.com/opensiddur/opensiddur-infra">
              Source code
            </a>
          </p>
          <p>
            Logo: Aharon Varady, © 2009–2014, from{" "}
            <a href="https://opensiddur.org/wp-content/uploads/2018/09/Open-Siddur-Project-Logo-2016.svg">
              the Open Siddur Project
            </a>
            , unchanged, under{" "}
            <a href="https://creativecommons.org/licenses/by-sa/4.0/">
              CC BY-SA 4.0
            </a>
            .
          </p>
          {notice ? (
            <>
              <p>Release {notice.release}</p>
              {notice.components.map((n: Value, i: number) => (
                <LicenseNotice key={i} notice={n} />
              ))}
            </>
          ) : (
            <p>Loading deployed notices…</p>
          )}
        </main>
      ) : path.startsWith("/share/") ? (
        <main>
          <h1>Your shared book</h1>
          {share ? (
            <>
              <p>
                Available until{" "}
                {new Date(share.expires * 1000).toLocaleString()}.
              </p>
              {share.artifacts.map((a: Value) => (
                <p key={a.name}>
                  <a
                    href={
                      "/api/v1/shares/" +
                      path.split("/")[2] +
                      "/files/" +
                      encodeURIComponent(a.name)
                    }
                  >
                    {a.name}
                  </a>
                </p>
              ))}
            </>
          ) : (
            <p>Loading shared artifacts…</p>
          )}
        </main>
      ) : (
        <>
          <section className="intro">
            <h1>Siddur builder</h1>
            <p>
              Select texts, translations and annotations from the{" "}
              <a href="https://opensiddur.org/">Open Siddur Project</a> to
              compile a prayerbook. Choose your customs and layout, then
              download your book.
            </p>
          </section>
          <main className="layout">
            <div className="builder-toolbar">
                <p className="hint"><RequiredMark /> Required fields. Empty required fields are highlighted.</p>
              <label className="check">
                <input
                  type="checkbox"
                  checked={advanced}
                  onChange={(e) => changeAdvanced(e.target.checked)}
                />
                Show advanced settings
              </label>
              <SettingHelp label="Show advanced settings">
                Includes starting files, the full settings editor, YAML and
                TeX/XML output. Saved with your presets.
              </SettingHelp>
            </div>
            <div className="configuration">

              <section className="card project">
                <SearchSelect
                  id="project"
                  required
                  label="Choose your starting text"
                  help="The starting text supplies the structure of your book. Use Text priorities to choose which editions supply its passages."
                  labelClassName="eyebrow"
                  options={projects.map((p: Value) => ({
                    value: p.id,
                    label: projectLabel(p),
                    keywords: p.id,
                  }))}
                  value={settings.book?.project || ""}
                  onSelect={choose}
                  allowClear
                  disabled={!catalog}
                />
                {!catalog && <p role="status">Loading project catalog…</p>}
                {selected && (
                  <>
                    <p className="selected-title">{projectLabel(selected)}</p>
                    {advanced && (
                      <details>
                        <summary>
                          Starting file
                          <SettingHelp label="Starting file">Choose which XML file in the starting text to compile. The index usually starts the complete work.</SettingHelp>
                        </summary>
                        <label>
                          Starting file
                          <select
                            value={settings.book?.file_name || "index.xml"}
                            onChange={(e) =>
                              setRoot("book", {
                                ...settings.book,
                                file_name: e.target.value,
                              })
                            }
                          >
                            {selected.files.map((file: string) => (
                              <option key={file} value={file}>
                                {file}
                              </option>
                            ))}
                          </select>
                        </label>
                      </details>
                    )}
                    <p>{selected.description}</p>
                    {selected.presets.length > 0 && (
                      <PublishedPresets
                        presets={selected.presets}
                        value={publishedPreset}
                        onChange={(value) => {
                          const preset = selected.presets[Number(value)];
                          if (!preset) return;
                          replaceSettings(preset.settings);
                          setPublishedPreset(value);
                          setAsset(null);
                          setMessage(
                            `Loaded ${preset.name.replaceAll("_", " ")} preset.`,
                          );
                        }}
                      />
                    )}
                  </>
                )}
              </section>
              <section className="card settings" key={settingsEpoch}>
                <h2>Settings</h2>
              <div className="load-settings">
                <h3>Load settings</h3>
                {user ? presets.length > 0 ? (
                  <SearchSelect
                    label="Load a saved preset"
                    help="Restore your saved book settings and output choices."
                    options={presets.map((preset) => ({ value: preset.id, label: preset.name }))}
                    value={loadedPreset}
                    disabled={loadingSettings}
                    onSelect={(id) => {
                      const preset = presets.find((item) => item.id === id);
                      if (preset) action(() => loadPreset(preset));
                    }}
                  />
                ) : <p className="hint">Your saved presets will appear here.</p>
                  : <p><a href="/#account" onClick={openAccount}>Sign in to load a saved preset.</a></p>}
                <label htmlFor="upload-settings">Upload settings YAML</label>
                <SettingHelp label="Upload settings YAML">Replace the current settings with the choices in a YAML file, then continue editing below.</SettingHelp>
                  <input id="upload-settings" type="file" accept=".yaml,.yml,application/yaml,text/yaml"
                    disabled={loadingSettings}
                    onChange={(event) => {
                      const file = event.currentTarget.files?.[0];
                      event.currentTarget.value = "";
                      if (file) action(() => importSettings(file));
                    }} />
                <p className="hint">Load a preset or a YAML file to replace the current settings, then continue editing below.</p>
                {loadingSettings && <p role="status">Loading settings…</p>}
              </div>
                {headerIssues.length > 0 && <p className="field-error" role="alert">{headerIssues[0]}</p>}
                {hasPendingSettings && (
                  <p role="status" className="hint">
                    Complete or cancel unfinished settings before previewing,
                    saving or creating a book.
                  </p>
                )}
                <div className="tabs" role="tablist">
                  {[
                    "Sources",
                    "Customs",
                    "Typography",
                    "Distribution",
                    ...(advanced ? ["Advanced"] : []),
                  ].map((t) => (
                    <button
                      role="tab"
                      aria-selected={tab === t}
                      key={t}
                      onClick={() => setTab(t)}
                    >
                      {t}
                    </button>
                  ))}
                </div>
                {tab === "Typography" && (
                  <p className="hint">
                    Choose fonts, text sizes and page layout. Use (default)
                    to leave a setting to the compiler. Print preview shows these changes.
                  </p>
                )}
                {tab === "Distribution" && (
                  <p className="hint">
                    Choose how attribution and licensing notices appear in your
                    book, and optionally add a logo.
                  </p>
                )}
                {tab === "Sources" && (
                  <>
                    <Sources
                      label="Text priorities"
                      projects={projects}
                      value={settings.priority?.transclusion || []}
                      onChange={(v) =>
                        setRoot("priority", {
                          ...settings.priority,
                          transclusion: v,
                        })
                      }
                    />
                    <Sources
                      label="Translation priorities"
                      projects={projects}
                      value={settings.parallel?.projects || []}
                      onChange={(v) =>
                        setRoot("parallel", {
                          ...settings.parallel,
                          projects: v,
                        })
                      }
                    />
                    <Sources
                      label="Instruction priorities"
                      projects={projects}
                      value={settings.priority?.instructions || []}
                      onChange={(v) =>
                        setRoot("priority", {
                          ...settings.priority,
                          instructions: v,
                        })
                      }
                    />
                    <Sources
                      label="Annotation sources"
                      projects={projects}
                      value={settings.annotations || []}
                      ordered={false}
                      onChange={(v) => setRoot("annotations", v)}
                    />
                    <p className="hint">
                      All matching annotations from selected sources are
                      included. Ordered lists use the first matching source.
                    </p>
                  </>
                )}
                {tab === "Customs" && (
                  <Declarations
                    registry={catalog?.features}
                    labels={catalog?.feature_labels}
                    defaults={catalog?.declaration_defaults}
                    value={settings.declarations || {}}
                    onChange={(v) => setRoot("declarations", v)}
                  />
                )}
                {tab === "Typography" && advanced && (
                  <details>
                    <summary>Installed font families</summary>
                    <p className="hint">{catalog?.fonts?.join(" · ")}</p>
                  </details>
                )}
                {schema &&
                  guided.map((key) => (
                    <SchemaField
                      key={key}
                      advanced={advanced}
                      label={key}
                      schema={schema.properties[key]}
                      root={schema}
                      value={settings[key]}
                      onChange={(v) => setRoot(key, v)}
                    />
                  ))}
                {tab === "Distribution" && (
                  <div>
                    <label htmlFor="upload-logo">Custom PNG/JPEG logo (5 MiB maximum)</label>
                    <SettingHelp label="Custom logo">Upload a logo to include with the book’s distribution notice.</SettingHelp>
                    <input
                      id="upload-logo"
                      type="file"
                      accept="image/png,image/jpeg"
                      disabled={!user || !hasConsent}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file)
                          action(async () => {
                            const result = await api(
                              "/assets",
                              "POST",
                              file,
                              true,
                            );
                            setAsset(result.id);
                            setMessage(
                              "Logo uploaded; it will accompany this build.",
                            );
                          });
                      }}
                    />
                    {asset && (
                      <button onClick={() => setAsset(null)}>
                        Remove uploaded logo
                      </button>
                    )}
                  </div>
                )}
                {tab === "Advanced" && (
                  <>
                    <p>
                      All processor settings are available below. Disabled
                      fields inherit processor defaults. Unset and explicitly
                      undefined values are distinct.
                    </p>
                    {schema &&
                      Object.entries(schema.properties).map(([key, s]) => (
                        <details key={key}>
                          <summary>{key}</summary>
                          <SchemaField
                            schema={s}
                            root={schema}
                            value={settings[key]}
                            label={key}
                            required={(schema.required || []).includes(key)}
                            onChange={(v) => setRoot(key, v)}
                          />
                        </details>
                      ))}
                    <div className="source-heading">
                      <h3>Settings YAML</h3>
                      <SettingHelp label="Settings YAML">Edit the book settings as YAML. Select Apply YAML to load your edits into the builder.</SettingHelp>
                    </div>
                    <textarea
                      aria-label="Settings YAML"
                      spellCheck={false}
                      rows={20}
                      value={yaml}
                      onChange={(e) => setYaml(e.target.value)}
                    />
                    <button
                      onClick={() =>
                        action(async () => {
                          const value = parse(yaml);
                          await applySettings(value);
                        })
                      }
                    >
                      Apply YAML
                    </button>

                  </>
                )}
                <div className="row">
                    <button
                      disabled={!settings.book || hasPendingSettings || loadingSettings}
                      onClick={() =>
                        localFile("settings.yaml", stringify(settings))
                      }
                    >
                      Save settings YAML
                    </button>

                  <button
                    disabled={
                      !user ||
                      !hasConsent ||
                      !settings.book ||
                      hasPendingSettings || loadingSettings
                    }
                    onClick={() => setSavingPreset(true)}
                  >
                    Save preset
                  </button>
                </div>
                {savingPreset && (
                  <PresetNameForm presets={presets} initialName={presets.find((preset) => preset.id === loadedPreset)?.name || ""}
                    onSave={save} onCancel={() => setSavingPreset(false)}
                    disabled={!user || !hasConsent || !settings.book || hasPendingSettings || loadingSettings} />
                )}
              </section>
              <section className="card output">
                <h2>Create your book</h2>
                <fieldset className={!formats.some((format) => advanced || ["pdf", "html"].includes(format)) ? "required-empty" : undefined}>
                  <legend>Output formats<RequiredMark />
                    <SettingHelp label="Output formats">Choose the files to create. PDF is for printing. HTML is a reflowable book you can read offline. TeX and XML are source files for further editing.</SettingHelp>
                  </legend>
                {["pdf", "html"].map((f) => (
                  <label className="check" key={f}>
                    <input
                      type="checkbox"
                      checked={formats.includes(f)}
                      onChange={(e) =>
                        setFormats(
                          e.target.checked
                            ? [...formats, f]
                            : formats.filter((x) => x !== f),
                        )
                      }
                    />
                    {f === "pdf" ? "Printable PDF" : "Offline HTML book"}
                  </label>
                ))}
                {advanced && (
                  <div className="advanced-formats">
                    <h3>Additional output formats</h3>
                    {["tex", "xml"].map((f) => (
                      <label className="check" key={f}>
                        <input
                          type="checkbox"
                          checked={formats.includes(f)}
                          onChange={(e) =>
                            setFormats(
                              e.target.checked
                                ? [...formats, f]
                                : formats.filter((x) => x !== f),
                            )
                          }
                        />
                        {f.toUpperCase()}
                      </label>
                    ))}
                  </div>
                )}
                </fieldset>
                <p className="hint">
                  Your settings are included with your downloads. Files are
                  available for 30 days. A full book may take several hours; you
                  can leave this page and return later. Compile one full book at
                  a time.
                </p>
                <Allowance allowances={account?.allowances} />
                {!user && (
                  <p>
                    <a href="/#account" onClick={openAccount}>
                      Sign in to create your book
                    </a>
                  </p>
                )}
                {user && !hasConsent && (
                  <p>
                    <a href="/#account" onClick={openAccount}>
                      Review processing consent to create your book
                    </a>
                  </p>
                )}
                <button
                  className="primary"
                  disabled={building || !!buildBlocker}
                  aria-describedby={buildBlocker ? "build-requirement" : undefined}
                  onClick={() => {
                    if (!user || !hasConsent) openAccount();
                    else action(() => build());
                  }}
                >
                  {building ? "Starting build…" : "Build"}
                </button>
                {buildBlocker && <p id="build-requirement" role="status" className="hint">{buildBlocker}</p>}
              </section>

              <section className="card preview">
                <h2>Preview your settings</h2>
                <p className="hint">
                  These synthetic Hebrew and English preview works demonstrate
                  title pages, headings, lists, notes, and paired and unpaired text.
                  Print preview shows typeset pages; text preview shows reflowing HTML.
                  Preview sources are supplied automatically. Your chosen source
                  priorities apply when you build the complete book.
                </p>
                <label htmlFor="preview-format">Preview format</label>
                <SettingHelp label="Preview format">Text shows a reflowable HTML sample. Print layout typesets a PDF sample to show how the pages will look in print.</SettingHelp>
                  <select id="preview-format" value={previewMode} onChange={(e) => setPreviewMode(e.target.value as "html" | "pdf")}>
                    <option value="html">Text (HTML)</option>
                    <option value="pdf">Print layout (PDF)</option>
                  </select>
                <SampleAllowance allowances={account?.allowances} />
                {previewMode === "pdf" && <p className="hint">
                  Typesetting takes longer than text preview.

                </p>}
                <p role="status" id="preview-requirement">
                  {!user ? (
                    <a href="/#account" onClick={openAccount}>
                      Sign in to see a sample
                    </a>
                  ) : !hasConsent ? (
                    <a href="/#account" onClick={openAccount}>
                      Review processing consent in your account to preview.
                    </a>
                  ) : previewBlocker ? (
                    previewBlocker
                  ) : (
                    previewStatus
                  )}
                </p>
                {preview && previewMode === "pdf" ? (
                  <>
                    <object
                      className="pdf-preview" data={preview} type="application/pdf"
                      aria-label="Print settings demonstration"
                    >
                      <p>Your browser cannot display this PDF.</p>
                    </object>
                    <p><a href={preview} download="sample.pdf">Download the print sample</a></p>
                  </>
                ) : preview ? (
                  <iframe
                    title="Settings demonstration"
                    sandbox=""
                    srcDoc={preview}
                  />
                ) : (
                  <div className="empty">Your sample will appear here.</div>
                )}
                <button
                  disabled={!!previewBlocker}
                  aria-describedby="preview-requirement"
                  onClick={() => {
                    if (!user || !hasConsent) openAccount();
                    else refreshPreview((n) => n + 1);
                  }}
                >
                  {previewMode === "pdf" ? "Update print sample" : "Update text sample"}
                </button>
              </section>
            </div>

          </main>

        </>
      )}
      <StatusUpdates current={updates.current} history={updates.history} onDismiss={updates.dismiss} />
      <footer>
        <a href="https://opensiddur.org/">the Open Siddur Project</a>
        <a href="/privacy">Privacy</a>
        <a href="/licenses">Software licenses & notices</a>
        <a href="https://github.com/opensiddur/opensiddur-infra">Source</a>
      </footer>
    </SettingsEditContext.Provider>
    </TypographyMetadata.Provider>
  );
}
