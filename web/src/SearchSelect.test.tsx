import React from "react";
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SearchSelect, searchMatches } from "./SearchSelect";
import { LicenseNotice, licenseLabel } from "./LicenseNotice";

describe("searchable catalog dropdown", () => {
  const options = [
    { value: "fallback", label: "Another edition", keywords: "siddur" },
    { value: "he", label: "Siddur Éxample · Hebrew" },
    { value: "en", label: "Siddur Éxample · English" },
  ];
  it("ranks title matches ahead of internal keywords and supports accents and multiple words", () => {
    expect(searchMatches(options, "siddur").map((o) => o.value)).toEqual([
      "he",
      "en",
      "fallback",
    ]);
    expect(searchMatches(options, "example heb").map((o) => o.value)).toEqual([
      "he",
    ]);
    expect(searchMatches(options, "not present")).toEqual([]);
  });
  it("uses one labelled editable combobox instead of a search input plus a select", () => {
    const html = renderToStaticMarkup(
      <SearchSelect
        label="Starting text"
        options={options}
        value="he"
        onSelect={() => {}}
      />,
    );
    expect(html).toContain('role="combobox"');
    expect(html).toContain('aria-autocomplete="list"');
    expect(html).toContain('aria-expanded="false"');
    expect(html).toContain('value="Siddur Éxample · Hebrew"');
    expect(html).not.toContain("<select");
  });
});

describe("license disclosure", () => {
  it("keeps full licence metadata inside the disclosure and only a short name in its summary", () => {
    const text =
      "The MIT License (MIT)\nCopyright (c) 2020 Example Author\nPermission is hereby granted to use this synthetic example.";
    const html = renderToStaticMarkup(
      <LicenseNotice
        notice={{
          name: "example",
          version: "1.0",
          license: text,
          source: "https://example.org",
          text: "",
        }}
      />,
    );
    const summary = html.match(/<summary>(.*?)<\/summary>/)?.[1];
    expect(summary).toBe("example 1.0 — MIT");
    expect(summary).not.toContain("Permission");
    expect(html).toContain("Copyright (c) 2020 Example Author");
    expect(html).toContain("<pre>");
    expect(licenseLabel("Unstructured ".repeat(50))).toBe("See license text");
  });
});
