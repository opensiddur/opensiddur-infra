// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { StatusUpdates, useStatusUpdates } from "./StatusUpdates";
function Example() {
  const updates = useStatusUpdates();
  return <>
    <button onClick={() => updates.info("Settings loaded.")}>Load settings</button>
    <button onClick={() => updates.error("Could not save.")}>Fail</button>
    <button onClick={updates.reset}>Sign out</button>
    <input aria-label="Continue editing" />
    <StatusUpdates {...updates} onDismiss={updates.dismiss} onDismissAll={updates.reset} />
  </>;
}
afterEach(() => { cleanup(); vi.useRealTimers(); });
it("clears the status automatically, retains expandable history and never takes editing focus", () => {
  vi.useFakeTimers();
  render(<Example />);
  const editor = screen.getByRole("textbox");
  editor.focus();
  fireEvent.click(screen.getByRole("button", { name: "Load settings" }));
  expect(document.activeElement).toBe(editor);
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("status").textContent).toBe("Settings loaded.");
  act(() => vi.advanceTimersByTime(8000));
  expect(screen.getByRole("status").textContent).toBe("Ready.");
  const expand = screen.getByRole("button", { name: "Notifications (1)" });
  fireEvent.click(expand);
  expect(expand.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByText("Settings loaded.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Close notification history" }));
  expect(screen.queryByText("Settings loaded.")).toBeNull();
  expect(expand.getAttribute("aria-expanded")).toBe("false");
});
it("dismisses a current message from history too, and can remove an expired message", () => {
  vi.useFakeTimers();
  render(<Example />);
  fireEvent.click(screen.getByRole("button", { name: "Load settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Dismiss current notification" }));
  expect(screen.getByRole("button", { name: "Notifications (0)" }).hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Load settings" }));
  act(() => vi.advanceTimersByTime(8000));
  fireEvent.click(screen.getByRole("button", { name: "Notifications (1)" }));
  fireEvent.click(screen.getByRole("button", { name: "Dismiss notification: Settings loaded." }));
  expect(screen.queryByText("Settings loaded.")).toBeNull();
  expect(screen.queryByRole("heading", { name: "Notifications" })).toBeNull();
});
it("keeps newer errors when an older history entry is dismissed and clears history on sign out", () => {
  render(<Example />);
  fireEvent.click(screen.getByRole("button", { name: "Load settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Fail" }));
  fireEvent.click(screen.getByRole("button", { name: "Notifications (2)" }));
  fireEvent.click(screen.getByRole("button", { name: "Dismiss notification: Settings loaded." }));
  expect(screen.getByRole("alert").textContent).toBe("Could not save.");
  expect(within(screen.getByRole("list")).getByText("Error: Could not save.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  expect(screen.queryByText("Error: Could not save.")).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
});
it("repeated messages get a fresh lifetime instead of being cleared by an earlier timer", () => {
  vi.useFakeTimers();
  render(<Example />);
  fireEvent.click(screen.getByRole("button", { name: "Load settings" }));
  act(() => vi.advanceTimersByTime(7000));
  fireEvent.click(screen.getByRole("button", { name: "Load settings" }));
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.getByRole("status").textContent).toBe("Settings loaded.");
  act(() => vi.advanceTimersByTime(7000));
  expect(screen.getByRole("status").textContent).toBe("Ready.");
  expect(screen.getByRole("button", { name: "Notifications (2)" })).toBeTruthy();
});
it("dismisses all notifications and allows new notifications afterwards", () => {
  vi.useFakeTimers();
  render(<Example />);
  fireEvent.click(screen.getByRole("button", { name: "Load settings" }));
  fireEvent.click(screen.getByRole("button", { name: "Fail" }));
  fireEvent.click(screen.getByRole("button", { name: "Notifications (2)" }));
  fireEvent.click(screen.getByRole("button", { name: "Dismiss All" }));
  expect(screen.queryByRole("heading", { name: "Notifications" })).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("status").textContent).toBe("Ready.");
  expect(screen.getByRole<HTMLButtonElement>("button", { name: "Notifications (0)" }).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Load settings" }));
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.getByRole("status").textContent).toBe("Settings loaded.");
  fireEvent.click(screen.getByRole("button", { name: "Notifications (1)" }));
  expect(within(screen.getByRole("list")).getByText("Settings loaded.")).toBeTruthy();
});
