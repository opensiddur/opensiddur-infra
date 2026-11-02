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
    expect(inherited).not.toContain("<select");
    expect(explicit).toContain("<select");
    expect(explicit).toContain('value="false" selected');
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
