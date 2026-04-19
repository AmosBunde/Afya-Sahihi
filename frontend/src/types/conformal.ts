export interface ConformalSet {
  /** Top answer and "also consider" alternatives within the set. */
  top_answer: string;
  also_consider: readonly string[];
  /** 1 − alpha target (e.g. 0.90 for 90% coverage). */
  target_coverage: number;
  /** Per-stratum q_hat that produced this set, rendered for debugging. */
  q_hat: number;
  /** Safety-critical categories that triggered strict review. */
  strata: readonly string[];
}
