import type { Value } from "./api";

/** Canonicalize the processor's documented shorthand for schema editing. */
export function normalizeSettings(input: Value): Value {
  const result = JSON.parse(JSON.stringify(input));
  const fonts = result?.typography?.fonts;
  if (fonts && typeof fonts === "object" && !Array.isArray(fonts)) {
    for (const [name, original] of Object.entries(fonts)) {
      let family: Value = original;
      if (typeof family === "string" || Array.isArray(family)) {
        family = { names: typeof family === "string" ? [family] : family };
      } else if (
        family &&
        typeof family === "object" &&
        !Object.hasOwn(family, "names") &&
        Object.hasOwn(family, "entries")
      ) {
        family = { ...family, names: family.entries };
        delete family.entries;
      }
      if (family && Array.isArray(family.names)) {
        family = {
          ...family,
          names: family.names.map((face: Value) =>
            typeof face === "string" ? { name: face } : face,
          ),
        };
      }
      Object.defineProperty(fonts, name, {
        value: family,
        enumerable: true,
        configurable: true,
        writable: true,
      });
    }
  }
  for (const key of ["page_header", "page_footer"]) {
    const heads = result?.typography?.[key];
    if (!heads || typeof heads !== "object") continue;
    for (const side of Object.values(heads) as Value[]) {
      if (!side || typeof side !== "object" || Array.isArray(side)) continue;
      for (const position of ["left", "center", "right"]) {
        if (typeof side[position] === "string")
          side[position] = { text: side[position] };
      }
    }
  }
  return result;
}
