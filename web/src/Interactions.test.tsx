// @vitest-environment jsdom
import React, { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { SearchSelect } from "./SearchSelect";
import { Sources } from "./Settings";
import { App } from "./App";
import { api, emailLink } from "./api";

vi.mock("./api", () => ({
  api: vi.fn(),
  auth: null,
  runtime: {},
  needsEmail: () => false,
  emailLink: vi.fn(),
  finishEmail: vi.fn(),
  logout: vi.fn(),
  google: vi.fn(),
  download: vi.fn(),
}));
const projects = [
  {
    id: "example-he",
    title: "Example Siddur",
    language: "he",
    files: ["index.xml"],
    presets: [],
  },
  {
    id: "example-en",
    title: "Example Siddur",
    language: "en",
    files: ["index.xml"],
    presets: [],
  },
  {
    id: "other",
    title: "Other Prayerbook",
    language: "en",
    files: ["index.xml"],
    presets: [],
  },
];
beforeEach(() => {
  window.history.replaceState({}, "", "/");
  localStorage.clear();
  sessionStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
  vi.mocked(api).mockImplementation(async (path) =>
    path === "/catalog"
      ? { projects, release: "synthetic", features: {} }
      : path === "/schema"
        ? { properties: {} }
        : path === "/notices"
          ? {
              release: "synthetic",
              components: [
                {
                  name: "Example package",
                  version: "1.0",
                  license:
                    "The MIT License (MIT)\nCopyright (c) Example Author\nPermission is hereby granted in this synthetic fixture.",
                  text: "",
                  source: "https://example.org",
                },
              ],
            }
          : {},
  );
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("autocomplete interactions", () => {
  it("shows matching options as typing changes and supports keyboard selection and Escape", () => {
    function Example() {
      const [value, setValue] = useState("");
      return (
        <SearchSelect
          label="Pick a title"
          options={[
            { value: "he", label: "Example Hebrew" },
            { value: "en", label: "Example English" },
            { value: "other", label: "Other book" },
          ]}
          value={value}
          onSelect={setValue}
        />
      );
    }
    render(<Example />);
    const input = screen.getByRole("combobox", {
      name: "Pick a title",
    }) as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Example" } });
    expect(screen.getAllByRole("option")).toHaveLength(2);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(input.value).toBe("Example English");
    expect(input.getAttribute("aria-expanded")).toBe("false");
    fireEvent.change(input, { target: { value: "nothing matches" } });
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    expect(screen.getByRole("status").textContent).toContain(
      "No matching titles",
    );
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input.value).toBe("Example English");
  });
  it("adds a source through the same dropdown, clears its query and excludes duplicates", () => {
    function Example() {
      const [value, setValue] = useState<string[]>([]);
      return (
        <Sources
          label="Translation priorities"
          projects={projects}
          value={value}
          onChange={setValue}
        />
      );
    }
    render(<Example />);
    const input = screen.getByRole("combobox", {
      name: "Add translation priorities",
    }) as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "English" } });
    fireEvent.click(
      screen.getByRole("option", { name: "Example Siddur · English" }),
    );
    expect(input.value).toBe("");
    expect(screen.getByText("Example Siddur · English")).toBeTruthy();
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "English" } });
    expect(
      screen.queryByRole("option", { name: "Example Siddur · English" }),
    ).toBeNull();
    expect(
      screen.getByRole("option", { name: "Other Prayerbook · English" }),
    ).toBeTruthy();
  });
});

describe("account access", () => {
  it("opens sign-in from the header and returns to the builder without losing the chosen book", async () => {
    render(<App />);
    const input = (await screen.findByRole("combobox", {
      name: "Choose your starting text",
    })) as HTMLInputElement;
    await waitFor(() => expect(input.disabled).toBe(false));
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Example Hebrew" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(input.value).toBe("Example Siddur · Hebrew");
    fireEvent.click(screen.getByText("Account", { selector: "summary" }));
    fireEvent.click(screen.getByRole("link", { name: "Sign in" }));
    expect(
      screen.getByRole("heading", { name: "Sign in" }),
    ).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Email address" })).toBeTruthy();
    expect(window.location.hash).toBe("#account");
    fireEvent.click(
      screen.getByRole("link", { name: "← Return to the builder" }),
    );
    expect(
      (
        screen.getByRole("combobox", {
          name: "Choose your starting text",
        }) as HTMLInputElement
      ).value,
    ).toBe("Example Siddur · Hebrew");
    expect(emailLink).not.toHaveBeenCalled();
  });
});

describe("license page interaction", () => {
  it("places full metadata license text in a collapsed disclosure with a concise summary", async () => {
    render(<App />);
    fireEvent.click(
      screen.getByRole("link", { name: "Software licenses" }),
    );
    const summary = await screen.findByText("Example package 1.0 — MIT", {
      selector: "summary",
    });
    const details = summary.closest("details")!;
    expect(details.open).toBe(false);
    expect(summary.textContent).not.toContain("Copyright");
    fireEvent.click(summary);
    expect(details.open).toBe(true);
    expect(details.querySelector("pre")?.textContent).toContain(
      "Permission is hereby granted in this synthetic fixture",
    );
  });
});
