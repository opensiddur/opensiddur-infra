import React from "react";
import { describe, it, expect } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PublishedPresets, Allowance } from "./BuilderControls";
import { Sources } from "./Settings";

describe("builder review regressions", () => {
  it("shows the loaded preset instead of resetting to a placeholder", () => {
    const html = renderToStaticMarkup(
      <PublishedPresets
        presets={[{ name: "undated" }, { name: "festival_edition" }]}
        value="0"
        onChange={() => {}}
      />,
    );
    expect(html).toContain('value="0" selected="">Undated');
    expect(html).not.toContain('value="" selected');
  });
  it("distinguishes translated editions by title and language and explains priority order", () => {
    const html = renderToStaticMarkup(
      <Sources
        label="Text priorities"
        projects={[
          { id: "internal-one", title: "Example Siddur", language: "he" },
          { id: "internal-two", title: "Example Siddur", language: "en" },
        ]}
        value={["internal-one", "internal-two"]}
        onChange={() => {}}
      />,
    );
    expect(html).toContain("Example Siddur · Hebrew");
    expect(html).toContain("Example Siddur · English");
    expect(html).not.toContain("internal-one");
    expect(html).toContain('aria-label="About Text priorities"');
    expect(html).toContain("first source in this list that contains it");
  });
  it("shows actual remaining books and minutes without the fixed daily limits", () => {
    const html = renderToStaticMarkup(
      <Allowance
        allowances={{ builds_remaining: 2, build_seconds_remaining: 600 }}
      />,
    );
    expect(html).toContain("2 books");
    expect(html).toContain("10 minutes");
    expect(html).not.toContain("UTC");
    expect(renderToStaticMarkup(<Allowance />)).toContain(
      "Sign in to see your remaining allowance",
    );
  });
});
