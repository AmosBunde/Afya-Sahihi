import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PredictionSet } from "../src/components/Conformal/PredictionSet";

describe("PredictionSet", () => {
  it("renders the top answer", () => {
    render(
      <PredictionSet
        set={{
          top_answer: "Amoxicillin 500mg tds",
          also_consider: ["Cefalexin 500mg qid"],
          target_coverage: 0.9,
          q_hat: 0.42,
          strata: ["dosing"],
        }}
      />,
    );
    expect(screen.getByText("Amoxicillin 500mg tds")).toBeInTheDocument();
  });

  it("renders also-consider with rounded coverage percent", () => {
    render(
      <PredictionSet
        set={{
          top_answer: "Top",
          also_consider: ["Alt A", "Alt B"],
          target_coverage: 0.9,
          q_hat: 0.1,
          strata: [],
        }}
      />,
    );
    expect(
      screen.getByText(/within 90% coverage/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Alt A")).toBeInTheDocument();
    expect(screen.getByText("Alt B")).toBeInTheDocument();
  });

  it("omits also-consider block when list is empty", () => {
    render(
      <PredictionSet
        set={{
          top_answer: "Only answer",
          also_consider: [],
          target_coverage: 0.9,
          q_hat: 0.1,
          strata: [],
        }}
      />,
    );
    expect(screen.queryByText(/also consider/i)).not.toBeInTheDocument();
  });

  it("has a labelled region for a11y", () => {
    render(
      <PredictionSet
        set={{
          top_answer: "x",
          also_consider: [],
          target_coverage: 0.9,
          q_hat: 0.1,
          strata: [],
        }}
      />,
    );
    expect(
      screen.getByRole("region", { name: /prediction set/i }),
    ).toBeInTheDocument();
  });
});
