// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, act, waitFor, within } from "@testing-library/react";
import { App } from "./App";
import { api, download } from "./api";
import { parse } from "yaml";

vi.mock("firebase/auth", () => ({
  onAuthStateChanged: (_: unknown, callback: Function) => {
    callback({ uid: "synthetic", getIdToken: async () => "synthetic-token" });
    return () => {};
  },
}));
vi.mock("./api", () => ({
  api: vi.fn(), auth: {}, runtime: {}, needsEmail: () => false,
  emailLink: vi.fn(), finishEmail: vi.fn(), logout: vi.fn(), google: vi.fn(), download: vi.fn(),
}));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); localStorage.clear(); vi.unstubAllGlobals(); });
it("keeps Typography in HTML until print layout is selected and refreshes the chosen format", async () => {
  vi.useFakeTimers();
  vi.mocked(api).mockClear();
  Element.prototype.scrollIntoView = vi.fn();
  window.history.replaceState({}, "", "/");
  let count = 0;
  vi.mocked(api).mockImplementation(async (path, method) => {
    if (path === "/catalog") return { release: "synthetic", features: {}, projects: [
      { id: "sample", title: "Sample", language: "he", files: ["index.xml"], presets: [] },
    ] };
    if (path === "/schema") return { properties: { typography: { type: "object", properties: {
      parallel: { type: "object", properties: { layout: { type: "string", enum: ["pages", "pairs", "interleaved"], default: "pairs" } } },
    } } } };
    if (path === "/account") return { consent: { version: "test" }, consent_version: "test", allowances: { pdf_samples_remaining: 10 } };
    if (path === "/builds" && method === "POST") return { id: "build-" + ++count };
    if (path.startsWith("/builds/")) return { state: "succeeded" };
    return [];
  });
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: true,
    text: async () => "<p>Sample</p>",
    blob: async () => new Blob(["%PDF-synthetic"], { type: "application/pdf" }),
  })));
  const revoke = vi.fn();
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:synthetic-" + count), revokeObjectURL: revoke }));
  await act(async () => { render(<App />); });
  const title = screen.getByRole("combobox", { name: "Choose your starting text" });
  fireEvent.focus(title);
  fireEvent.change(title, { target: { value: "Sample" } });
  fireEvent.keyDown(title, { key: "Enter" });
  fireEvent.click(screen.getByRole("tab", { name: "Typography" }));
  const format = screen.getByRole<HTMLSelectElement>("combobox", { name: "Preview format" });
  expect(format.value).toBe("html");
  fireEvent.click(screen.getByText("parallel", { selector: "summary" }));
  const layout = screen.getByRole("combobox", { name: "layout" });
  const choose = (name: string) => fireEvent.change(layout, { target: { value: Array.from((layout as HTMLSelectElement).options).find(o => o.text === name)!.value } });
  choose("pages");
  await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
  expect(screen.getByTitle("Settings demonstration")).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "Sources" }));
  fireEvent.click(screen.getByRole("tab", { name: "Typography" }));
  expect(format.value).toBe("html");
  expect(screen.getByTitle("Settings demonstration")).toBeTruthy();
  fireEvent.change(format, { target: { value: "pdf" } });
  await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
  expect(screen.getByLabelText("Print settings demonstration").getAttribute("data")).toBe("blob:synthetic-2");
  const currentLayout = screen.getByRole<HTMLSelectElement>("combobox", { name: "layout" });
  fireEvent.change(currentLayout, { target: { value: Array.from(currentLayout.options).find(o => o.text === "pairs")!.value } });
  expect(screen.queryByLabelText("Print settings demonstration")).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
  const builds = vi.mocked(api).mock.calls.filter(([path, method]) => path === "/builds" && method === "POST");
  expect(builds.map(call => [call[2].type, call[2].settings.typography.parallel.layout])).toEqual([["html", "pages"], ["pdf", "pages"], ["pdf", "pairs"]]);
  expect(screen.getByLabelText("Print settings demonstration").getAttribute("data")).toBe("blob:synthetic-3");
  expect(revoke).toHaveBeenCalledWith("blob:synthetic-2");
  vi.unstubAllGlobals();
});

it("saves and renames presets without prompts and keeps build history in its own tab", async () => {
  vi.mocked(api).mockClear();
  Element.prototype.scrollIntoView = vi.fn();
  window.history.replaceState({}, "", "/");
  const prompt = vi.spyOn(window, "prompt").mockImplementation(() => { throw new Error("prompt() is not supported"); });
  let presets: any[] = [];
  vi.mocked(api).mockImplementation(async (path, method, data) => {
    if (path === "/catalog") return { release: "synthetic", features: {}, projects: [
      { id: "sample", title: "Sample", language: "he", files: ["index.xml"], presets: [] },
    ] };
    if (path === "/schema") return { properties: {} };
    if (path === "/account") return { consent: { version: "test" }, consent_version: "test", allowances: { samples: { html: { used: 3, limit: 300 }, pdf: { used: 1, limit: 10 } } } };
    if (path === "/presets") return presets;
    if (path === "/builds") return [
      { id: "synthetic-history", title: "Synthetic work", type: "full", state: "succeeded", stage: "Finished", artifacts: [{ name: "book.pdf" }] },
      { id: "active-history", title: "Active work", type: "full", state: "running", stage: "Compiling active text", artifacts: [] },
      { id: "hidden-sample", type: "html", state: "running", stage: "Sample-only stage", artifacts: [] },
    ];
    if (path.startsWith("/presets/") && method === "PUT") { presets = [{ ...data, id: path.split("/").pop() }]; return {}; }
    return [];
  });
  await act(async () => { render(<App />); });
  const title = screen.getByRole("combobox", { name: "Choose your starting text" });
  fireEvent.focus(title);
  fireEvent.change(title, { target: { value: "Sample" } });
  fireEvent.keyDown(title, { key: "Enter" });
  fireEvent.click(screen.getByRole("button", { name: "Save preset" }));
  expect(screen.getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(true);
  fireEvent.change(screen.getByRole("textbox", { name: "Preset name" }), { target: { value: "  My siddur  " } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await screen.findByText("Preset saved until you delete it.");
  expect(presets[0]).toMatchObject({
    name: "My siddur",
    settings: {
      book: { project: "sample" },
      priority: { transclusion: ["sample"] },
    },
    preferences: { advanced: false, formats: ["pdf", "html"] },
  });
  fireEvent.click(screen.getByText("Account", { selector: "summary" }));
  fireEvent.click(screen.getByRole("link", { name: "Account & saved presets" }));
  fireEvent.click(screen.getByText("Saved presets & account controls"));
  fireEvent.click(screen.getByRole("button", { name: "Rename" }));
  expect((screen.getByRole("textbox", { name: "Preset name" }) as HTMLInputElement).value).toBe("My siddur");
  fireEvent.change(screen.getByRole("textbox", { name: "Preset name" }), { target: { value: "Renamed siddur" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Renamed siddur" })).toBeTruthy());
  expect(presets[0].preferences).toEqual({ advanced: false, formats: ["pdf", "html"] });
  fireEvent.click(screen.getByRole("link", { name: "← Return to the builder" }));
  expect(screen.queryByText("synthetic-history")).toBeNull();
  fireEvent.click(screen.getByRole("link", { name: "Build history" }));
  expect(window.location.pathname).toBe("/builds");
  expect(screen.getByRole("heading", { name: "Build history" })).toBeTruthy();
  expect(screen.getByText("Synthetic work · Complete")).toBeTruthy();
  expect(screen.getByText("Samples today: 3 of 300 text; 1 of 10 print.")).toBeTruthy();
  expect(screen.queryByText("Sample-only stage")).toBeNull();
  expect(screen.getAllByRole("link", { name: "View build" })).toHaveLength(2);
  expect(screen.getByText("Active work · Running")).toBeTruthy();
  expect(screen.getByText("Compiling active text")).toBeTruthy();
  expect(screen.queryByText("Finished")).toBeNull();
  expect(screen.queryByRole("button", { name: "book.pdf" })).toBeNull();
  expect(screen.getAllByRole("link", { name: "View build" })[0].getAttribute("href")).toBe("/builds/synthetic-history");
  fireEvent.click(screen.getByRole("link", { name: "Builder" }));
  expect((screen.getByRole("combobox", { name: "Choose your starting text" }) as HTMLInputElement).value).toBe("Sample · Hebrew");
  expect(screen.queryByText("synthetic-history")).toBeNull();
  expect(prompt).not.toHaveBeenCalled();
});

it("opens the submitted full build and polls through completion to downloads", async () => {
  vi.useFakeTimers();
  vi.mocked(api).mockClear();
  Element.prototype.scrollIntoView = vi.fn();
  window.history.replaceState({}, "", "/");
  let polls = 0;
  const queued = { id: "new-build", type: "full", state: "queued", stage: "Waiting", artifacts: [] };
  vi.mocked(api).mockImplementation(async (path, method, data) => {
    if (path === "/catalog") return { release: "synthetic", features: {}, projects: [
      { id: "sample", title: "Sample", language: "he", files: ["index.xml"], presets: [] },
    ] };
    if (path === "/schema") return { properties: {} };
    if (path === "/account") return { consent: { version: "test" }, consent_version: "test", allowances: { samples: { html: { used: 3, limit: 300 }, pdf: { used: 1, limit: 10 } } } };
    if (path === "/builds" && method === "POST") return data.type === "full" ? queued : { id: "preview" };
    if (path === "/builds/new-build") return ++polls === 1
      ? { ...queued, state: "running", stage: "Typesetting PDF" }
      : { ...queued, state: "succeeded", stage: "Finished", artifacts: [{ name: "book.pdf" }, { name: "worker.log" }] };
    if (path === "/builds/preview") return { state: "cancelled", results: {} };
    return [];
  });
  await act(async () => { render(<App />); });
  const title = screen.getByRole("combobox", { name: "Choose your starting text" });
  fireEvent.focus(title);
  fireEvent.change(title, { target: { value: "Sample" } });
  fireEvent.keyDown(title, { key: "Enter" });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Build" })); });
  expect(window.location.pathname).toBe("/builds/new-build");
  expect(screen.getByRole("heading", { name: "Build status" })).toBeTruthy();
  expect(screen.getByText("Running: Typesetting PDF")).toBeTruthy();
  const submitted = vi.mocked(api).mock.calls.find(([path, method, data]) => path === "/builds" && method === "POST" && data.type === "full")!;
  expect(submitted[2]).toMatchObject({ settings: { book: { project: "sample" } }, formats: ["pdf", "html"] });
  await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
  expect(screen.getByText("Complete: Finished")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Download worker.log" }).closest("details") as HTMLDetailsElement).open).toBe(false);
  fireEvent.click(screen.getByText("Details", { selector: "summary" }));
  fireEvent.click(screen.getByRole("button", { name: "Download worker.log" }));
  expect(vi.mocked(download)).toHaveBeenCalledWith("/builds/new-build/files/worker.log", "worker.log");
  expect(screen.getByRole("button", { name: "book.pdf" })).toBeTruthy();
  fireEvent.click(screen.getByRole("link", { name: "Builder" }));
  expect((screen.getByRole("combobox", { name: "Choose your starting text" }) as HTMLInputElement).value).toBe("Sample · Hebrew");
});

it("loads saved presets and YAML files from Settings, preserving values and rejecting invalid imports", async () => {
  vi.mocked(api).mockClear();
  Element.prototype.scrollIntoView = vi.fn();
  window.history.replaceState({}, "", "/");
  const preset = { id: "saved", name: "My saved settings", asset: "owned-logo",
    preferences: { advanced: true, formats: ["pdf"] },
    settings: { book: { project: "sample", file_name: "index.xml" }, typography: { parallel: { layout: "pages" } }, declarations: { custom: { enabled: false, count: 0 } } },
  };
  vi.mocked(api).mockImplementation(async (path, method, data) => {
    if (path === "/catalog") return { release: "synthetic", features: {}, projects: [
      { id: "sample", title: "Sample", language: "he", files: ["index.xml"], presets: [] },
      { id: "other", title: "Other", language: "en", files: ["index.xml"], presets: [] },
    ] };
    if (path === "/schema") return { properties: { typography: { type: "object", properties: { caption: { type: "string", minLength: 2 } } } } };
    if (path === "/account") return { consent: { version: "test" }, consent_version: "test" };
    if (path === "/presets") return [preset];
    if (path === "/validate") return { settings: data };
    return [];
  });
  await act(async () => { render(<App />); });
  let load = screen.getByRole("combobox", { name: "Load a saved preset" });
  expect(load.closest("section")?.querySelector("h2")?.textContent).toBe("Settings");
  expect(load.closest("section")?.querySelector(".load-settings")?.nextElementSibling?.getAttribute("role")).toBe("tablist");
  const starting = screen.getByRole("combobox", { name: "Choose your starting text" });
  fireEvent.focus(starting);
  fireEvent.change(starting, { target: { value: "Other" } });
  fireEvent.keyDown(starting, { key: "Enter" });
  fireEvent.click(screen.getByRole("tab", { name: "Typography" }));
  fireEvent.click(screen.getByText(/^typography/i, { selector: "summary" }));
  fireEvent.change(screen.getByRole("textbox", { name: "caption" }), { target: { value: "A" } });
  expect(screen.getByRole("button", { name: "Build" }).hasAttribute("disabled")).toBe(true);
  load = screen.getByRole("combobox", { name: "Load a saved preset" });
  fireEvent.focus(load);
  fireEvent.change(load, { target: { value: "My saved" } });
  fireEvent.keyDown(load, { key: "Enter" });
  await screen.findByText("Loaded My saved settings.");
  await waitFor(() => expect(screen.getByRole("button", { name: "Build" }).hasAttribute("disabled")).toBe(false));
  await waitFor(() => expect((screen.getByRole("combobox", { name: "Choose your starting text" }) as HTMLInputElement).value).toBe("Sample · Hebrew"));
  expect((screen.getByRole("checkbox", { name: "Show advanced settings" }) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole("checkbox", { name: "Offline HTML book" }) as HTMLInputElement).checked).toBe(false);
  fireEvent.click(screen.getByRole("tab", { name: "Advanced" }));
  expect(parse((screen.getByRole("textbox", { name: "Settings YAML" }) as HTMLTextAreaElement).value)).toEqual(preset.settings);
  const upload = (text: string) => {
    const file = new File([text], "settings.yaml", { type: "text/yaml" });
    Object.defineProperty(file, "text", { value: async () => text });
    fireEvent.change(screen.getByLabelText("Upload settings YAML"), { target: { files: [file] } });
  };
  upload("book:\n  project: other\n  file_name: index.xml\ntypography:\n  fonts:\n    latin: Example Font\ndeclarations:\n  custom:\n    enabled: false\n    count: 0\n    empty: null\n");
  await screen.findByText("Settings loaded.");
  await waitFor(() => expect((screen.getByRole("combobox", { name: "Choose your starting text" }) as HTMLInputElement).value).toBe("Other · English"));
  fireEvent.click(screen.getByRole("tab", { name: "Advanced" }));
  const imported = parse((screen.getByRole("textbox", { name: "Settings YAML" }) as HTMLTextAreaElement).value);
  expect(imported.typography.fonts.latin.names).toEqual([{ name: "Example Font" }]);
  expect(imported.declarations.custom).toEqual({ enabled: false, count: 0, empty: null });
  upload("- invalid\n- settings\n");
  await screen.findByText("Settings must be a mapping");
  await waitFor(() => expect((screen.getByRole("combobox", { name: "Choose your starting text" }) as HTMLInputElement).value).toBe("Other · English"));
  const saveFile = screen.getByRole("button", { name: "Save settings YAML" });
  expect(saveFile.parentElement).toBe(screen.getByRole("button", { name: "Save preset" }).parentElement);
  fireEvent.click(screen.getByRole("button", { name: "Save preset" }));
  fireEvent.change(screen.getByRole("combobox", { name: "Preset name" }), { target: { value: "Imported" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await screen.findByText("Preset saved until you delete it.");
  const saved = vi.mocked(api).mock.calls.find(([path, method]) => path.startsWith("/presets/") && method === "PUT")!;
  expect(saved[2].asset).toBeNull();
  expect(saved[2].settings).toEqual(imported);
  fireEvent.click(screen.getByRole("button", { name: "Save preset" }));
  const overwrite = screen.getByRole("combobox", { name: "Preset name" });
  fireEvent.focus(overwrite);
  fireEvent.change(overwrite, { target: { value: "My saved" } });
  fireEvent.keyDown(overwrite, { key: "Enter" });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(vi.mocked(api).mock.calls.some(([path, method]) => path === "/presets/saved" && method === "PUT")).toBe(true));
  const replaced = vi.mocked(api).mock.calls.find(([path, method]) => path === "/presets/saved" && method === "PUT")!;
  expect(replaced[2].settings).toEqual(imported);
  expect(replaced[2].name).toBe("My saved settings");
  await waitFor(() => expect(screen.queryByRole("combobox", { name: "Preset name" })).toBeNull());

});

it.each(["html", "pdf"] as const)("refreshes the selected %s sample without switching its format", async (mode) => {
  vi.useFakeTimers();
  vi.mocked(api).mockClear();
  window.history.replaceState({}, "", "/");
  let count = 0;
  vi.mocked(api).mockImplementation(async (path, method) => {
    if (path === "/catalog") return { release: "synthetic", features: {}, projects: [
      { id: "sample", title: "Sample", language: "he", files: ["index.xml"], presets: [] },
    ] };
    if (path === "/schema") return { properties: {} };
    if (path === "/account") return { consent: { version: "test" }, consent_version: "test", allowances: { pdf_samples_remaining: 10 } };
    if (path === "/builds" && method === "POST") return { id: "sample-" + ++count };
    if (path.startsWith("/builds/")) return { state: "succeeded" };
    return [];
  });
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, text: async () => "<p>Sample</p>", blob: async () => new Blob(["%PDF-synthetic"]) })));
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:sample-" + count), revokeObjectURL: vi.fn() }));
  await act(async () => { render(<App />); });
  const title = screen.getByRole("combobox", { name: "Choose your starting text" });
  fireEvent.focus(title);
  fireEvent.change(title, { target: { value: "Sample" } });
  fireEvent.keyDown(title, { key: "Enter" });
  const format = screen.getByRole("combobox", { name: "Preview format" }) as HTMLSelectElement;
  fireEvent.change(format, { target: { value: mode } });
  await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
  fireEvent.click(screen.getByRole("button", { name: mode === "html" ? "Update text sample" : "Update print sample" }));
  await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
  expect(format.value).toBe(mode);
  const submissions = vi.mocked(api).mock.calls.filter(([path, method]) => path === "/builds" && method === "POST");
  expect(submissions).toHaveLength(2);
  expect(submissions.map(call => [call[2].type, call[2].formats])).toEqual([[mode, [mode]], [mode, [mode]]]);
  expect(mode === "html" ? screen.getByTitle("Settings demonstration") : screen.getByLabelText("Print settings demonstration")).toBeTruthy();
});

it("keeps history logs inside collapsed details for active and finished builds", async () => {
  window.history.replaceState({}, "", "/builds");
  vi.mocked(download).mockClear();
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/catalog") return { release: "synthetic", features: {}, projects: [] };
    if (path === "/schema") return { properties: {} };
    if (path === "/account") return { consent: { version: "test" }, consent_version: "test" };
    if (path === "/builds") return [
      { id: "active", title: "Active work", type: "full", state: "running", stage: "Typesetting", artifacts: [{ name: "worker.log" }] },
      { id: "finished", title: "Finished work", type: "full", state: "failed", stage: "Private failure details", artifacts: [{ name: "pdf.log" }] },
    ];
    return [];
  });
  await act(async () => { render(<App />); });
  for (const log of screen.getAllByRole("button", { name: /Download .*\.log/ })) {
    expect((log.closest("details") as HTMLDetailsElement).open).toBe(false);
  }
  const active = within(screen.getByText("Active work · Running").closest("article")!);
  const finished = within(screen.getByText("Finished work · Failed").closest("article")!);
  for (const [entry, id, filename] of [[active, "active", "worker.log"], [finished, "finished", "pdf.log"]] as const) {
    fireEvent.click(entry.getByText("Details", { selector: "summary" }));
    fireEvent.click(entry.getByRole("button", { name: "Download " + filename }));
    expect(vi.mocked(download)).toHaveBeenCalledWith(`/builds/${id}/files/${filename}`, filename);
    fireEvent.click(entry.getByText("Details", { selector: "summary" }));
    expect((entry.getByRole("button", { name: "Download " + filename }).closest("details") as HTMLDetailsElement).open).toBe(false);
  }
  expect(screen.queryByText("Private failure details")).toBeNull();
  expect(finished.queryByText("Detailed steps were not recorded for this build yet.")).toBeNull();
});

it("sorts work titles newest first on initial load and after polling", async () => {
  vi.useFakeTimers();
  window.history.replaceState({}, "", "/builds");
  let reads = 0;
  const older = { id: "older", title: "Older work", created: 10, type: "full", state: "succeeded", artifacts: [] };
  const newer = { id: "newer", title: "Newer work", created: 20, type: "full", state: "succeeded", artifacts: [] };
  const newest = { id: "newest", title: "Newest work", created: 30, type: "full", state: "running", artifacts: [] };
  vi.mocked(api).mockImplementation(async path => {
    if (path === "/catalog") return { release: "synthetic", features: {}, projects: [] };
    if (path === "/schema") return { properties: {} };
    if (path === "/account") return {};
    if (path === "/builds") return ++reads === 1 ? [older, newer] : [older, newest, newer];
    return [];
  });
  await act(async () => { render(<App />); });
  const titles = () => Array.from(document.querySelectorAll("article strong")).map(node => node.textContent);
  expect(titles()).toEqual(["Newer work · Complete", "Older work · Complete"]);
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(titles()).toEqual(["Newest work · Running", "Newer work · Complete", "Older work · Complete"]);
});
