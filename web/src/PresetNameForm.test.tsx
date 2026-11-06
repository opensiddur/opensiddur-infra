// @vitest-environment jsdom
import React from "react";
import { expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PresetNameForm } from "./PresetNameForm";

it("keeps the entered name when saving fails and supports cancelling", async () => {
  const save = vi.fn(async () => { throw new Error("Temporary failure"); });
  const cancel = vi.fn();
  render(<PresetNameForm onSave={save} onCancel={cancel} />);
  const input = screen.getByRole("textbox", { name: "Preset name" }) as HTMLInputElement;
  fireEvent.change(input, { target: { value: "My settings" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Temporary failure");
  expect(input.value).toBe("My settings");
  expect(save).toHaveBeenCalledWith("My settings", undefined);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(cancel).toHaveBeenCalledOnce();
  cleanup();
});


it("chooses an overwrite target from the dropdown and preserves a new typed name after blur", async () => {
  Element.prototype.scrollIntoView = vi.fn();
  const save = vi.fn(async (_name: string, _id?: string) => {});
  render(<PresetNameForm presets={[{ id: "existing", name: "Existing siddur" }]}
    onSave={save} onCancel={() => {}} />);
  const input = screen.getByRole("combobox", { name: "Preset name" }) as HTMLInputElement;
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: "Existing" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(screen.getByText("Saving will replace the settings in “Existing siddur”.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(save).toHaveBeenCalledWith("Existing siddur", "existing"));
  await waitFor(() => expect(input.disabled).toBe(false));
  fireEvent.change(input, { target: { value: "New siddur" } });
  fireEvent.blur(input);
  expect(input.value).toBe("New siddur");
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(save).toHaveBeenCalledWith("New siddur", undefined));
  cleanup();
});
