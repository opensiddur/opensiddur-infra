// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FontSelect, TypographyMetadata, runningHeadIssues, templateError } from "./TypographyControls";
import { SchemaField, SettingsEditContext } from "./SchemaField";
afterEach(cleanup);
const codes = ["page", "document-title", "chapter-number", "section-title"];
it("validates the running-title grammar and doubled literal braces", () => {
  for (const text of ["", "My siddur", "Page {page}", "{{{page}}}", "{document-title} · {section-title}"]) expect(templateError(text, codes)).toBeUndefined();
  expect(templateError("{unknown}", codes)).toContain("Unknown placeholder");
  expect(templateError("{page", codes)).toContain("Missing closing");
  expect(templateError("page}", codes)).toContain("Unmatched");
  expect(runningHeadIssues({ page_header: { all: {}, odd: {} } }, codes)[0]).toContain("rather than both");
  expect(runningHeadIssues({ page_footer: { odd: { left: { text: "{unknown}" } } } }, codes)[0]).toContain("Unknown placeholder");
  expect(runningHeadIssues({ page_footer: { odd: { left: { language: "English" } } } }, codes)[0]).toContain("language tag");
});
it("offers installed fonts in capability sections without a free-text name input", () => {
  const onChange = vi.fn();
  render(<FontSelect id="font" label="Font name" value="Pointed" family="hebrew" required onChange={onChange}
    catalog={{ installed: ["Pointed", "Consonants", "Latin"], hebrew: [
      { label: "Hebrew with vowels and cantillation", fonts: ["Pointed"] },
      { label: "Hebrew consonants only", fonts: ["Consonants"] },
    ], latin: [{ label: "Installed Latin fonts", fonts: ["Latin"] }], other: [] }} />);
  expect(screen.queryByRole("textbox")).toBeNull();
  const select = screen.getByRole("combobox", { name: "Font name" });
  expect(select.querySelectorAll("optgroup")).toHaveLength(2);
  expect(screen.queryByRole("option", { name: "Latin" })).toBeNull();
  fireEvent.change(select, { target: { value: "Consonants" } });
  expect(onChange).toHaveBeenCalledWith("Consonants");
});
it("provides header help and reports invalid templates as pending edits", () => {
  const report = vi.fn();
  const root = { type: "object", properties: { page_header: { type: "object", properties: { all: { type: "object", properties: { center: { type: "object", properties: { text: { type: "string" } } } } } } } } };
  const example = (text: string) => <TypographyMetadata.Provider value={{ codes }}><SettingsEditContext.Provider value={report}>
    <SchemaField label="typography" schema={root} root={root} value={{ page_header: { all: { center: { text } } } }} onChange={vi.fn()} />
  </SettingsEditContext.Provider></TypographyMetadata.Provider>;
  const { rerender } = render(example("{bad}"));
  const field = screen.getByRole("textbox", { name: "text" });
  expect(field.getAttribute("aria-invalid")).toBe("true");
  expect(screen.getByRole("alert").textContent).toContain("Unknown placeholder");
  expect(report.mock.calls.some(([, pending]) => pending)).toBe(true);
  fireEvent.click(screen.getByLabelText("About page header"));
  expect(screen.getAllByText("{page}").length).toBeGreaterThan(0);
  rerender(example("Page {page}"));
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("status").textContent).toBe("Valid header/footer template.");
});
