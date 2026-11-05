// @vitest-environment jsdom
import React, { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { SchemaField, SettingsEditContext } from "./SchemaField";
import { MeasurementField, measurementModel } from "./MeasurementField";
afterEach(cleanup);
const length = { type: "string", pattern: "^-?(?:\\d+(?:\\.\\d+)?|\\.\\d+)(?:pt|mm|em|ex)$" };
const absolute = { type: "string", pattern: "^(?:\\d+(?:\\.\\d+)?|\\.\\d+)(?:pt|mm|cm)$" };
it("edits the amount and unit independently and keeps reset/inherited values distinct", () => {
  const changed = vi.fn();
  function Example() {
    const [value, setValue] = useState<any>();
    return <SchemaField label="spacing" schema={{ ...length, default: "0.5em" }} root={{}} value={value} onChange={v => { changed(v); setValue(v); }} />;
  }
  render(<Example />);
  const amount = screen.getByRole("spinbutton", { name: "spacing" }) as HTMLInputElement;
  const unit = screen.getByRole("combobox", { name: "spacing unit" }) as HTMLSelectElement;
  expect(amount.value).toBe("0.5"); expect(unit.value).toBe("em"); expect(changed).not.toHaveBeenCalled();
  fireEvent.change(amount, { target: { value: "2" } }); expect(changed).toHaveBeenLastCalledWith("2em");
  fireEvent.change(unit, { target: { value: "mm" } }); expect(changed).toHaveBeenLastCalledWith("2mm");
  fireEvent.change(amount, { target: { value: "-1.25" } }); expect(changed).toHaveBeenLastCalledWith("-1.25mm");
  fireEvent.click(screen.getByRole("button", { name: "(default)" }));
  expect(changed).toHaveBeenLastCalledWith(undefined); expect(amount.value).toBe("0.5"); expect(unit.value).toBe("em");
});
it("retains named sizes while allowing custom amounts only in schema-supported units", () => {
  const changed = vi.fn(); const pending = vi.fn();
  function Example() {
    const [value, setValue] = useState<any>("small");
    return <SettingsEditContext.Provider value={pending}><SchemaField label="size" schema={{ anyOf: [{ type: "string", enum: ["small", "large"] }, absolute, { type: "null" }] }} root={{}} value={value} onChange={v => { changed(v); setValue(v); }} /></SettingsEditContext.Provider>;
  }
  render(<Example />);
  fireEvent.change(screen.getByRole("combobox", { name: "size choice" }), { target: { value: "measure" } });
  expect(pending.mock.calls.some(([, value]) => value === true)).toBe(true);
  const units = screen.getByRole("combobox", { name: "size unit" });
  expect(Array.from((units as HTMLSelectElement).options).map(o => o.value)).toEqual(["pt", "mm", "cm"]);
  expect(screen.queryByRole("option", { name: "em" })).toBeNull();
  fireEvent.change(screen.getByRole("spinbutton", { name: "size amount" }), { target: { value: "-2" } });
  expect(changed).not.toHaveBeenCalled(); expect(screen.getByRole("alert")).toBeTruthy();
  fireEvent.change(screen.getByRole("spinbutton", { name: "size amount" }), { target: { value: "12" } });
  expect(changed).toHaveBeenLastCalledWith("12pt"); expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.change(screen.getByRole("combobox", { name: "size choice" }), { target: { value: "undefined" } });
  expect(changed).toHaveBeenLastCalledWith(null);
});
it("handles percent-or-length settings using the union of allowed units", () => {
  const model = measurementModel([{ type: "string", pattern: "^(?:\\d+(?:\\.\\d+)?|\\.\\d+)%$" }, absolute])!;
  expect(model.units).toEqual(["%", "pt", "mm", "cm"]);
  const changed = vi.fn();
  render(<MeasurementField id="width" label="width" model={model} value="43%" defaultValue={null} nullable required={false} reportPending={vi.fn()} onChange={changed} />);
  expect((screen.getByRole("spinbutton", { name: "width" }) as HTMLInputElement).value).toBe("43");
  expect((screen.getByRole("combobox", { name: "width unit" }) as HTMLSelectElement).value).toBe("%");
  fireEvent.change(screen.getByRole("combobox", { name: "width unit" }), { target: { value: "cm" } });
  expect(changed).toHaveBeenLastCalledWith("43cm");
});
it("keeps numeric point sizes as numbers and blocks incomplete or nonpositive edits", () => {
  const changed = vi.fn(), pending = vi.fn();
  render(<MeasurementField id="normal" label="normal size" model={{ units: ["pt"], patterns: [] }} value={12} defaultValue={null}
    nullable required={false} numericPoints schema={{ exclusiveMinimum: 0 }} reportPending={pending} onChange={changed} />);
  const amount = screen.getByRole("spinbutton", { name: "normal size" });
  fireEvent.change(amount, { target: { value: "14" } }); expect(changed).toHaveBeenLastCalledWith(14);
  changed.mockClear();
  fireEvent.change(amount, { target: { value: "0" } }); expect(changed).not.toHaveBeenCalled(); expect(screen.getByRole("alert")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "(default)" })); expect(changed).toHaveBeenLastCalledWith(undefined); expect(screen.queryByRole("alert")).toBeNull();
});
