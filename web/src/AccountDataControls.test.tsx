// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { AccountDataControls } from "./AccountDataControls";
import { api, deletionStatus, download, reauthenticateGoogle, emailReauthentication, finishEmail, needsEmail, type User } from "./api";
vi.mock("./api", () => ({ api: vi.fn(), deletionStatus: vi.fn(), download: vi.fn(),
  reauthenticateGoogle: vi.fn(), emailReauthentication: vi.fn(), finishEmail: vi.fn(), needsEmail: vi.fn(() => false) }));
const user = { uid: "reader", email: "reader@example.test", providerData: [{ providerId: "google.com" }] } as User;
const deleting = vi.fn(), deleted = vi.fn(async () => {});
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks(); localStorage.clear(); sessionStorage.clear();
  vi.mocked(needsEmail).mockReturnValue(false);
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(() => { cleanup(); vi.useRealTimers(); });
function show() { render(<AccountDataControls user={user} preferences={{ advanced: true }} onDeleting={deleting} onDeleted={deleted} />); }
async function click(button: HTMLElement) { await act(async () => { fireEvent.click(button); }); }
it("exports browser preferences once, polls, and downloads the ZIP", async () => {
  vi.mocked(api).mockResolvedValueOnce({ id: "export", state: "queued", phase: "Preparing download" })
    .mockResolvedValueOnce({ id: "export", state: "running", phase: "Collecting files" })
    .mockResolvedValueOnce({ id: "export", state: "succeeded", phase: "Download ready" });
  show();
  await click(screen.getByRole("button", { name: "Download all my data" }));
  expect(api).toHaveBeenCalledWith("/account/export", "POST", { browser_preferences: { advanced: true } });
  expect((screen.getByRole("button", { name: "Download all my data" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  await click(screen.getByRole("button", { name: "Download ZIP" }));
  expect(download).toHaveBeenCalledWith("/account/exports/export/download", "account-data.zip");
});
it("requires exact DELETE, supports cancellation, then clears browser data after confirmed cleanup", async () => {
  vi.mocked(api).mockResolvedValue({ state: "queued" });
  vi.mocked(deletionStatus).mockResolvedValueOnce({ state: "running", phase: "Removing files" })
    .mockResolvedValueOnce({ state: "succeeded", phase: "Deleted" });
  localStorage.setItem("builder-advanced", "true"); localStorage.setItem("unrelated", "keep");
  sessionStorage.setItem("loginEmail", user.email!);
  show();
  await click(screen.getByRole("button", { name: "Delete my account" }));
  let dialog = screen.getByRole("dialog");
  const confirm = within(dialog).getByRole("button", { name: "Permanently delete my account" });
  expect((confirm as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(within(dialog).getByLabelText("Type DELETE to confirm"), { target: { value: "delete" } });
  expect((confirm as HTMLButtonElement).disabled).toBe(true);
  await click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(api).not.toHaveBeenCalled();
  await click(screen.getByRole("button", { name: "Delete my account" }));
  dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Type DELETE to confirm"), { target: { value: "DELETE" } });
  await click(within(dialog).getByRole("button", { name: "Permanently delete my account" }));
  expect(deleting).toHaveBeenCalledOnce(); expect(deleted).not.toHaveBeenCalled();
  expect(screen.getByText("Removing files")).toBeTruthy();
  const body = vi.mocked(api).mock.calls[0][2];
  expect(body.confirmation).toBe("DELETE"); expect(body.receipt).toHaveLength(64);
  await act(async () => { await vi.advanceTimersByTimeAsync(2000); });
  expect(deleted).toHaveBeenCalledOnce();
  expect(localStorage.getItem("builder-advanced")).toBeNull();
  expect(sessionStorage.getItem("loginEmail")).toBeNull();
  expect(localStorage.getItem("unrelated")).toBe("keep");
  expect(screen.getByText("Your account and data have been deleted.")).toBeTruthy();
});
it("offers recent sign-in and requires confirmation again", async () => {
  vi.mocked(api).mockRejectedValue(Object.assign(new Error("Sign in again"), { status: 401 }));
  vi.mocked(deletionStatus).mockRejectedValue(new Error("No receipt"));
  show();
  await click(screen.getByRole("button", { name: "Delete my account" }));
  const dialog = screen.getByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Type DELETE to confirm"), { target: { value: "DELETE" } });
  await click(within(dialog).getByRole("button", { name: "Permanently delete my account" }));
  await click(within(dialog).getByRole("button", { name: "Email me a confirmation sign-in link" }));
  expect(emailReauthentication).toHaveBeenCalledOnce();
  await click(within(dialog).getByRole("button", { name: "Sign in again with Google" }));
  expect(reauthenticateGoogle).toHaveBeenCalledOnce();
  expect((within(dialog).getByLabelText("Type DELETE to confirm") as HTMLInputElement).value).toBe("");
  expect((within(dialog).getByRole("button", { name: "Permanently delete my account" }) as HTMLButtonElement).disabled).toBe(true);
});
it("resumes receipt polling after reload and retries a temporary status failure", async () => {
  sessionStorage.setItem("account-deletion-receipt", "receipt");
  vi.mocked(deletionStatus).mockRejectedValueOnce(new Error("Unavailable"))
    .mockResolvedValueOnce({ state: "succeeded", phase: "Deleted" });
  await act(async () => { show(); });
  expect(screen.getByRole("alert").textContent).toContain("retrying automatically");
  await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
  expect(deleted).toHaveBeenCalledOnce();
});
it("keeps email-link reauthentication reachable before reopening confirmation", async () => {
  sessionStorage.setItem("account-delete-pending", "true");
  vi.mocked(needsEmail).mockReturnValue(true);
  show();
  expect(screen.queryByRole("dialog")).toBeNull();
  await click(screen.getByRole("button", { name: "Finish signing in to confirm deletion" }));
  expect(finishEmail).toHaveBeenCalledWith(user.email);
  expect(screen.getByRole("dialog")).toBeTruthy();
  expect((screen.getByLabelText("Type DELETE to confirm") as HTMLInputElement).value).toBe("");
});
