// @vitest-environment jsdom
import React, { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { Declarations } from "./Settings";
import { TypographyMetadata } from "./TypographyControls";
import {
  SchemaField,
  resolve,
  numericChoices,
  SettingsEditContext,
} from "./SchemaField";
afterEach(cleanup);

it("sets a built-in font family from the installed catalog in standard mode", () => {
  const changed = vi.fn();
  const schema = {
    type: "object",
    properties: {
      fonts: { type: "object", additionalProperties: { $ref: "#/$defs/FontFamily" } },
    },
    $defs: {
      FontFamily: {
        type: "object",
        required: ["names"],
        properties: {
          names: {
            type: "array",
            minItems: 1,
            items: {
              type: "object",
              required: ["name"],
              properties: { name: { type: "string" } },
            },
          },
        },
      },
    },
  };
  render(
    <TypographyMetadata.Provider value={{ fonts: {
      installed: ["Example Hebrew", "Example Latin"],
      hebrew: [{ label: "Hebrew fonts", fonts: ["Example Hebrew"] }],
      latin: [{ label: "Latin fonts", fonts: ["Example Latin"] }],
      other: [],
    } }}>
      <SchemaField label="typography" schema={schema} root={schema}
        value={undefined} onChange={changed} advanced={false} expanded />
    </TypographyMetadata.Provider>,
  );
  fireEvent.click(screen.getByText("fonts", { selector: "summary" }));
  const hebrew = screen.getByText("hebrew", { selector: "summary" });
  fireEvent.click(hebrew);
  const family = within(hebrew.closest("details")!);
  fireEvent.click(family.getByText("names", { selector: "summary" }));
  fireEvent.click(family.getByRole("button", { name: "Add item" }));
  fireEvent.change(family.getByRole("combobox", { name: /name/ }), {
    target: { value: "Example Hebrew" },
  });
  fireEvent.click(family.getByRole("button", { name: "Add to list" }));
  expect(changed).toHaveBeenLastCalledWith({
    fonts: { hebrew: { names: [{ name: "Example Hebrew" }] } },
  });
});

const root = {
  $defs: {
    Layout: { type: "string", enum: ["pages", "pairs", "interleaved"] },
  },
};
function pick(select: HTMLElement, label: string) {
  const option = within(select).getByRole("option", {
    name: label,
  }) as HTMLOptionElement;
  fireEvent.change(select, { target: { value: option.value } });
}

describe("typed settings and defaults", () => {
  it("opens parallel settings without changing data and commits only the chosen layout", () => {
    const changed = vi.fn();
    const schema = {
      type: "object",
      properties: { layout: { $ref: "#/$defs/Layout", default: "pairs" } },
    };
    function Example() {
      const [value, setValue] = useState<unknown>();
      return (
        <SchemaField
          schema={schema}
          root={root}
          value={value}
          label="parallel"
          onChange={(v) => {
            changed(v);
            setValue(v);
          }}
        />
      );
    }
    const { container } = render(<Example />);
    fireEvent.click(screen.getByText("parallel", { selector: "summary" }));
    expect(changed).not.toHaveBeenCalled();
    expect(container.querySelectorAll('input[type="checkbox"]')).toHaveLength(
      0,
    );
    const select = screen.getByRole("combobox", { name: "layout" });
    expect((select as HTMLSelectElement).value).toBe("");
    expect(screen.getByText("Default: pairs.")).toBeTruthy();
    pick(select, "pages");
    expect(changed).toHaveBeenLastCalledWith({ layout: "pages" });
    pick(select, "(default)");
    expect(changed).toHaveBeenLastCalledWith(undefined);
    expect(resolve(schema.properties.layout, root).default).toBe("pairs");
  });
  it("uses a bounded integer dropdown and preserves default, false and null as distinct values", () => {
    const changed = vi.fn();
    render(
      <SchemaField
        label="depth"
        schema={{ type: "integer", minimum: 1, maximum: 4, default: 4 }}
        root={{}}
        value={undefined}
        onChange={changed}
      />,
    );
    const range = screen.getByRole("combobox", { name: "depth" });
    expect(
      within(range)
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["(default)", "1", "2", "3", "4"]);
    pick(range, "2");
    expect(changed).toHaveBeenLastCalledWith(2);
    cleanup();
    render(
      <SchemaField
        label="Include notes"
        schema={{
          anyOf: [{ type: "boolean" }, { type: "null" }],
          default: false,
        }}
        root={{}}
        value={undefined}
        onChange={changed}
      />,
    );
    const boolean = screen.getByRole("combobox", { name: "Include notes" });
    pick(boolean, "No");
    expect(changed).toHaveBeenLastCalledWith(false);
    pick(boolean, "(undefined)");
    expect(changed).toHaveBeenLastCalledWith(null);
    pick(boolean, "(default)");
    expect(changed).toHaveBeenLastCalledWith(undefined);
  });
  it("keeps unrestricted text and numbers editable and supports resetting an override", () => {
    const changed = vi.fn();
    render(
      <SchemaField
        label="Title"
        schema={{ type: "string" }}
        root={{}}
        value={undefined}
        onChange={changed}
      />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Title" }), {
      target: { value: "My book" },
    });
    expect(changed).toHaveBeenLastCalledWith("My book");
    fireEvent.click(screen.getByRole("button", { name: "(default)" }));
    expect(changed).toHaveBeenLastCalledWith(undefined);
    cleanup();
    render(
      <SchemaField
        label="Size"
        schema={{ type: "number", exclusiveMinimum: 0 }}
        root={{}}
        value={undefined}
        onChange={changed}
      />,
    );
    fireEvent.change(screen.getByRole("spinbutton", { name: "Size" }), {
      target: { value: "12.5" },
    });
    expect(changed).toHaveBeenLastCalledWith(12.5);
  });
  it("retains arbitrary valid values in continuous ranges through a custom number field", () => {
    const changed = vi.fn();
    render(
      <SchemaField
        label="Spacing"
        schema={{ type: "number", minimum: 0.5, maximum: 3, default: 1 }}
        root={{}}
        value={undefined}
        onChange={changed}
      />,
    );
    pick(screen.getByRole("combobox", { name: "Spacing" }), "Custom value…");
    expect(changed).not.toHaveBeenCalled();
    fireEvent.change(
      screen.getByRole("spinbutton", { name: "Spacing custom value" }),
      { target: { value: "1.25" } },
    );
    expect(changed).toHaveBeenLastCalledWith(1.25);
    expect(
      numericChoices({ type: "integer", minimum: 1, exclusiveMaximum: 3.5 })
        ?.values,
    ).toEqual([1, 2, 3]);
    expect(
      numericChoices({
        type: "number",
        minimum: 0,
        maximum: 0.3,
        multipleOf: 0.1,
      })?.values,
    ).toEqual([0, 0.1, 0.2, 0.3]);
  });
  it("holds incomplete required objects and new array items outside submitted settings", () => {
    const changed = vi.fn();
    const pending = vi.fn();
    const schema = {
      type: "object",
      required: ["first", "second"],
      properties: {
        first: { type: "string", minLength: 1 },
        second: { type: "string", minLength: 1 },
      },
    };
    render(
      <SettingsEditContext.Provider value={pending}>
        <SchemaField
          label="Entry"
          expanded
          schema={schema}
          root={{}}
          value={undefined}
          onChange={changed}
        />
      </SettingsEditContext.Provider>,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "first" }), {
      target: { value: "One" },
    });
    expect(changed).not.toHaveBeenCalled();
    expect(pending).toHaveBeenCalledWith(expect.any(String), true);
    fireEvent.change(screen.getByRole("textbox", { name: "second" }), {
      target: { value: "Two" },
    });
    expect(changed).toHaveBeenLastCalledWith({ first: "One", second: "Two" });
    cleanup();
    changed.mockClear();
    render(
      <SchemaField
        label="Fonts"
        expanded
        schema={{
          type: "array",
          minItems: 1,
          items: {
            type: "object",
            required: ["name"],
            properties: { name: { type: "string", minLength: 1 } },
          },
        }}
        root={{}}
        value={undefined}
        onChange={changed}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Add item" }));
    expect(changed).not.toHaveBeenCalled();
    expect(
      (screen.getByRole("button", { name: "Add to list" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "name" }), {
      target: { value: "Example Font" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add to list" }));
    expect(changed).toHaveBeenLastCalledWith([{ name: "Example Font" }]);
  });
});

it("edits Customs enums and numeric ranges directly without a Set-value activation step", () => {
  const changed = vi.fn();
  const registry = {
    "opensiddur:example": {
      features: {
        count: { numeric: { min: 1, max: 3 } },
        choice: { symbol: { values: ["first", "second"] } },
      },
    },
  };
  render(
    <Declarations
      registry={registry}
      labels={{}}
      value={{ "opensiddur:example": {} }}
      onChange={changed}
    />,
  );
  expect(changed).not.toHaveBeenCalled();
  const count = screen.getByRole("combobox", { name: "count" });
  pick(count, "2");
  expect(changed).toHaveBeenLastCalledWith({
    "opensiddur:example": { count: 2 },
  });
  const choice = screen.getByRole("combobox", { name: "choice" });
  pick(choice, "second");
  expect(changed).toHaveBeenLastCalledWith({
    "opensiddur:example": { choice: "second" },
  });
  pick(choice, "(undefined)");
  expect(changed).toHaveBeenLastCalledWith({ "opensiddur:example": { choice: null } });
});

it("distinguishes explicit empty text from resetting to default", () => {
  const changed = vi.fn();
  render(
    <SchemaField
      label="Header text"
      schema={{ type: "string", default: "Inherited header" }}
      root={{}}
      value="Custom header"
      onChange={changed}
    />,
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Header text" }), {
    target: { value: "" },
  });
  expect(changed).toHaveBeenLastCalledWith("");
  fireEvent.click(screen.getByRole("button", { name: "(default)" }));
  expect(changed).toHaveBeenLastCalledWith(undefined);
});
it("keeps a required font entry while its name is cleared and replaced", () => {
  const changed = vi.fn();
  render(
    <SchemaField
      label="Font"
      expanded
      schema={{
        type: "object",
        required: ["name"],
        properties: {
          name: { type: "string", minLength: 1 },
          normal_size: { type: "number" },
        },
      }}
      root={{}}
      value={{ name: "Old Font", normal_size: 12 }}
      onChange={changed}
    />,
  );
  const name = screen.getByRole("textbox", { name: "name" });
  fireEvent.change(name, { target: { value: "" } });
  expect(changed).not.toHaveBeenCalled();
  expect(screen.getByRole("textbox", { name: "name" })).toBe(name);
  fireEvent.change(name, { target: { value: "New Font" } });
  expect(changed).toHaveBeenLastCalledWith({
    name: "New Font",
    normal_size: 12,
  });
});

it("marks required empty values without marking defaults or treating zero and false as empty", () => {
  const schema = { type: "object", required: ["name", "count", "enabled", "layout"], properties: {
    name: { type: "string", minLength: 1 },
    count: { type: "integer" },
    enabled: { type: "boolean" },
    layout: { type: "string", enum: ["pages", "pairs"], default: "pairs" },
  } };
  function Example() {
    const [value, setValue] = useState({ name: "", count: 0, enabled: false });
    return <SchemaField schema={schema} root={{}} value={value} label="Example" onChange={setValue} />;
  }
  const { container } = render(<Example />);
  const name = screen.getByRole("textbox", { name: "name" });
  expect(name.getAttribute("aria-required")).toBe("true");
  expect(name.getAttribute("aria-invalid")).toBe("true");
  expect(name.classList.contains("required-empty")).toBe(true);
  expect(screen.getByRole("spinbutton", { name: "count" }).getAttribute("aria-invalid")).toBeNull();
  expect(screen.getByRole("combobox", { name: "enabled" }).getAttribute("aria-invalid")).toBeNull();
  expect(screen.getByRole("combobox", { name: "layout" }).getAttribute("aria-required")).toBeNull();
  expect(container.querySelectorAll(".required-marker")).toHaveLength(3);
  fireEvent.change(name, { target: { value: "My font" } });
  expect(name.getAttribute("aria-invalid")).toBeNull();
});

it("shows actual Customs defaults, including false and zero, without writing inherited values", () => {
  const changed = vi.fn();
  render(<Declarations
    registry={{ example: { features: {
      enabled: "binary", disabled: "binary", day: { numeric: { min: 0, max: 3 } },
      count: { numeric: { min: 0 } }, choice: { symbol: { values: ["one", "two"] } }, unset: "binary",
    } } }}
    labels={{}} defaults={{ example: { enabled: true, disabled: false, day: 0, count: 12, choice: "two" } }}
    value={{ example: {} }} onChange={changed} />);
  const selectedText = (name: string) => {
    const field = screen.getByRole("combobox", { name }) as HTMLSelectElement;
    return field.selectedOptions[0].text;
  };
  expect(selectedText("enabled")).toBe("Yes");
  expect(selectedText("disabled")).toBe("No");
  expect(selectedText("day")).toBe("0");
  expect(selectedText("choice")).toBe("two");
  expect(selectedText("unset")).toBe("(undefined)");
  expect((screen.getByRole("spinbutton", { name: "count" }) as HTMLInputElement).value).toBe("12");
  expect(screen.queryByRole("option", { name: "(default)" })).toBeNull();
  expect(changed).not.toHaveBeenCalled();
  pick(screen.getByRole("combobox", { name: "disabled" }), "Yes");
  expect(changed).toHaveBeenLastCalledWith({ example: { disabled: true } });
  pick(screen.getByRole("combobox", { name: "enabled" }), "(undefined)");
  expect(changed).toHaveBeenLastCalledWith({ example: { enabled: null } });
});
