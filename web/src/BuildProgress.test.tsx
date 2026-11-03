// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { BuildProgress } from "./BuildProgress";
afterEach(cleanup);
it("expands real step states and updates the current PDF pass", () => {
  const build = { steps: [
    { id: "compile-print", label: "Compile print text", state: "succeeded" },
    { id: "pdf", label: "Typeset PDF", state: "running", pass_number: 2 },
    { id: "upload", label: "Publish files", state: "pending" },
  ] };
  const { container, rerender } = render(<BuildProgress build={build} />);
  fireEvent.click(screen.getByText("Details", { selector: "summary" }));
  expect(container.querySelector('details')?.open).toBe(true);
  expect(screen.getByRole("img", { name: "Complete" }).textContent).toBe("✓");
  expect(screen.getByText(/PDF pass 2/)).toBeTruthy();
  expect(container.querySelector('.step-pending')?.textContent).toContain('Publish files');
  rerender(<BuildProgress build={{ steps: build.steps.map(step => step.id === 'pdf' ? { ...step, state:'failed', pass_number:3 } : step) }} />);
  expect(screen.getByRole("img", { name:"Failed" }).textContent).toBe("✕");
  expect(screen.getByText(/PDF pass 3/)).toBeTruthy();
});
it("uses recorded output outcomes for older builds without inventing pass counts", () => {
  render(<BuildProgress build={{ results: { html:{state:'succeeded'}, pdf:{state:'failed'} } }} />);
  expect(screen.getByText('HTML')).toBeTruthy();
  expect(screen.getByRole('img',{name:'Failed'})).toBeTruthy();
  expect(screen.queryByText(/PDF pass/)).toBeNull();
});
