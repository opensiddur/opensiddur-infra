import type { Value } from "./api";

export function licenseLabel(value?: string): string {
  const text = value?.trim() || "See license text";
  if (/^(?:the\s+)?MIT\s+License\b/i.test(text)) return "MIT";
  if (!/[\r\n]/.test(text) && text.length <= 100) return text;
  return "See license text";
}
export function LicenseNotice({ notice }: { notice: Value }) {
  const raw = String(notice.license || "");
  const text = [
    ...new Set(
      [licenseLabel(raw) !== raw.trim() ? raw : "", notice.text || ""]
        .map((s) => s.trim())
        .filter(Boolean),
    ),
  ].join("\n\n");
  return (
    <details>
      <summary>
        {notice.name} {notice.version} — {licenseLabel(raw)}
      </summary>
      <a href={notice.source}>Source</a>
      <pre>{text || "See linked upstream license."}</pre>
    </details>
  );
}
