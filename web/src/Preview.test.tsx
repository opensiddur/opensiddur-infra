// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, act, waitFor } from "@testing-library/react";
import { App } from "./App";
import { api } from "./api";

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
it("switches Typography to real PDF previews and regenerates when Pages changes to Pairs", async () => {
  vi.useFakeTimers();
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
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, blob: async () => new Blob(["%PDF-synthetic"], { type: "application/pdf" }) })));
  const revoke = vi.fn();
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:synthetic-" + count), revokeObjectURL: revoke }));
  await act(async () => { render(<App />); });
  const title = screen.getByRole("combobox", { name: "Choose your starting text" });
  fireEvent.focus(title);
  fireEvent.change(title, { target: { value: "Sample" } });
  fireEvent.keyDown(title, { key: "Enter" });
  fireEvent.click(screen.getByRole("tab", { name: "Typography" }));
  expect((screen.getByRole("combobox", { name: "Preview format" }) as HTMLSelectElement).value).toBe("pdf");
  fireEvent.click(screen.getByText("parallel", { selector: "summary" }));
  const layout = screen.getByRole("combobox", { name: "layout" });
  const choose = (name: string) => fireEvent.change(layout, { target: { value: Array.from((layout as HTMLSelectElement).options).find(o => o.text === name)!.value } });
  choose("pages");
  await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
  expect(screen.getByLabelText("Print settings demonstration").getAttribute("data")).toBe("blob:synthetic-1");
  choose("pairs");
  expect(screen.queryByLabelText("Print settings demonstration")).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
  const builds = vi.mocked(api).mock.calls.filter(([path, method]) => path === "/builds" && method === "POST");
  expect(builds.map(call => [call[2].type, call[2].settings.typography.parallel.layout])).toEqual([["pdf", "pages"], ["pdf", "pairs"]]);
  expect(screen.getByLabelText("Print settings demonstration").getAttribute("data")).toBe("blob:synthetic-2");
  expect(revoke).toHaveBeenCalledWith("blob:synthetic-1");
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
      { id: "synthetic-history", type: "full", state: "succeeded", stage: "Finished", artifacts: [{ name: "book.pdf" }] },
      { id: "active-history", type: "full", state: "running", stage: "Compiling active text", artifacts: [] },
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
  expect(presets[0]).toMatchObject({ name: "My siddur", settings: { book: { project: "sample" } }, preferences: { advanced: false, formats: ["pdf", "html"] } });
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
  expect(screen.getByText("Book · Complete")).toBeTruthy();
  expect(screen.getByText("Samples today: 3 of 300 text; 1 of 10 print.")).toBeTruthy();
  expect(screen.queryByText("Sample-only stage")).toBeNull();
  expect(screen.getAllByRole("link", { name: "View build" })).toHaveLength(2);
  expect(screen.getByText("Book · Running")).toBeTruthy();
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
      : { ...queued, state: "succeeded", stage: "Finished", artifacts: [{ name: "book.pdf" }] };
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
  expect(screen.getByRole("button", { name: "book.pdf" })).toBeTruthy();
  fireEvent.click(screen.getByRole("link", { name: "Builder" }));
  expect((screen.getByRole("combobox", { name: "Choose your starting text" }) as HTMLInputElement).value).toBe("Sample · Hebrew");
});
