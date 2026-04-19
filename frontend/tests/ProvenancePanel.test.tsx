import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProvenancePanel } from "../src/components/Provenance/ProvenancePanel";
import type { Citation } from "../src/types/provenance";

function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    chunk_id: "c-1",
    document_id: "doc-1",
    document_title: "MoH Paediatric Dosing Guidelines",
    section_path: ["Antibiotics", "Amoxicillin"],
    bounding_box: { page: 42, x0: 0.1, y0: 0.2, x1: 0.5, y1: 0.4 },
    similarity_score: 0.91,
    ...overrides,
  };
}

describe("ProvenancePanel", () => {
  it("renders nothing when citations list is empty", () => {
    const { container } = render(<ProvenancePanel citations={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows each citation's title and page", () => {
    render(<ProvenancePanel citations={[citation()]} />);
    expect(
      screen.getByText("MoH Paediatric Dosing Guidelines"),
    ).toBeInTheDocument();
    expect(screen.getByText(/page 42/i)).toBeInTheDocument();
  });

  it("calls onSelect when a citation is clicked", async () => {
    const user = userEvent.setup();
    const handle = vi.fn();
    const c = citation();
    render(<ProvenancePanel citations={[c]} onSelect={handle} />);
    await user.click(screen.getByRole("button"));
    expect(handle).toHaveBeenCalledWith(c);
  });

  it("labels each citation button for screen readers", () => {
    render(<ProvenancePanel citations={[citation()]} />);
    expect(
      screen.getByRole("button", {
        name: /open citation for moh paediatric dosing guidelines, page 42/i,
      }),
    ).toBeInTheDocument();
  });
});
