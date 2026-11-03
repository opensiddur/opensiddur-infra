// @vitest-environment jsdom
import React from "react";
import { expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  expect(save).toHaveBeenCalledWith("My settings");
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(cancel).toHaveBeenCalledOnce();
  cleanup();
});
