import React from "react";
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SchemaField } from "./Settings";
describe("settings control semantics", () => {
  it("distinguishes inherited false from explicit false", () => {
    const base = {
      schema: { type: "boolean", default: false },
      root: {},
      label: "Include notes",
      onChange: () => {},
    };
    const inherited = renderToStaticMarkup(
      <SchemaField {...base} value={undefined} />,
    );
    const explicit = renderToStaticMarkup(
      <SchemaField {...base} value={false} />,
    );
    expect(inherited).toContain('value="" selected="">(default)');
    expect(explicit).toContain('value="1" selected="">No');
    expect(inherited).not.toContain('type="checkbox"');
  });
  it("escapes labels and text supplied by schema metadata", () => {
    const rendered = renderToStaticMarkup(
      <SchemaField
        schema={{ type: "string" }}
        root={{}}
        label={"<script>bad()</script>"}
        value={"<img src=x onerror=bad()>"}
        onChange={() => {}}
      />,
    );
    expect(rendered).not.toContain("<script>");
    expect(rendered).toContain("&lt;script&gt;");
    expect(rendered).not.toContain("<img");
  });
});

import { normalizeSettings } from "./settings-data";
describe("legacy preset typography editing", () => {
  it("renders both shorthand and structured font faces as editable names without mutating the preset", () => {
    const input = {
      typography: {
        fonts: {
          hebrew: ["Example Font", { name: "Fallback Font", normal_size: 12 }],
        },
      },
    };
    const result = normalizeSettings(input);
    const root = {
      $defs: {
        Family: {
          type: "object",
          properties: {
            names: {
              type: "array",
              items: {
                type: "object",
                properties: {
                  name: { type: "string" },
                  normal_size: { type: "number" },
                },
              },
            },
          },
        },
      },
    };
    const html = renderToStaticMarkup(
      <SchemaField
        schema={{ $ref: "#/$defs/Family" }}
        root={root}
        value={result.typography.fonts.hebrew}
        label="Hebrew fonts"
        onChange={() => {}}
      />,
    );
    expect(html).toContain('value="Example Font"');
    expect(html).toContain('value="Fallback Font"');
    expect(html).toContain('value="12"');
    expect(input.typography.fonts.hebrew[0]).toBe("Example Font");
  });
  it("preserves processor aliases and unrelated settings when loading older canonical output", () => {
    const result = normalizeSettings({
      typography: {
        fonts: { latin: { entries: [{ name: "Latin Font" }] } },
        instructions: { from: "both" },
      },
      declarations: { "opensiddur:quorum": { minyan: false } },
    });
    expect(result.typography.fonts.latin.names[0].name).toBe("Latin Font");
    expect(result.typography.fonts.latin.entries).toBeUndefined();
    expect(result.typography.instructions.from).toBe("both");
    expect(result.declarations["opensiddur:quorum"].minyan).toBe(false);
  });
});

it("normalizes running-header shorthand without changing text or explicit conditions", () => {
  const input = {
    typography: {
      page_header: {
        all: {
          left: "Example header",
          right: { text: "{page}", if: "condition" },
        },
      },
      page_footer: { odd: { center: "Example footer" } },
    },
  };
  const result = normalizeSettings(input);
  expect(result.typography.page_header.all.left).toEqual({
    text: "Example header",
  });
  expect(result.typography.page_header.all.right).toEqual({
    text: "{page}",
    if: "condition",
  });
  expect(result.typography.page_footer.odd.center).toEqual({
    text: "Example footer",
  });
  expect(input.typography.page_header.all.left).toBe("Example header");
});
