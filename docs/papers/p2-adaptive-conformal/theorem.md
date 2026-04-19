# Theorem: clinical-harm-weighted coverage under covariate shift

**Draft statement.** Proof pending (issue #39 acceptance).

## Setup

Let $(X_1, Y_1), \ldots, (X_n, Y_n)$ be calibration observations from the source distribution $P_{\text{source}}$, and $(X_{\text{test}}, Y_{\text{test}})$ a test observation from the target distribution $P_{\text{target}}$. Assume the distributions differ only in covariates:

$$P_{\text{target}}(X, Y) = r(X) \cdot P_{\text{source}}(X, Y)$$

where $r(x) = \frac{dP_{\text{target}}}{dP_{\text{source}}}(x)$ is the likelihood ratio.

Let $s(x, y)$ be a nonconformity score and $h(x)$ a non-negative harm function defined on clinical strata (e.g., $h(x) = 3$ for dosing queries, $h(x) = 1$ for general queries).

## Statement

**Theorem (clinical-harm-weighted coverage).** Let $\hat{q}_\alpha$ be the $(1 - \alpha)$-quantile of the weighted empirical distribution

$$\sum_{i=1}^n \tilde{w}_i \cdot \delta_{s(X_i, Y_i)}$$

where $\tilde{w}_i = \frac{r(X_i) \cdot h(X_i)}{\sum_{j=1}^n r(X_j) \cdot h(X_j)}$ are normalised harm-weighted likelihood ratios. Define the prediction set

$$C(X_{\text{test}}) = \{y : s(X_{\text{test}}, y) \leq \hat{q}_\alpha\}.$$

Then

$$\mathbb{E}_{P_{\text{target}}}\left[ h(X_{\text{test}}) \cdot \mathbf{1}\{ Y_{\text{test}} \in C(X_{\text{test}}) \} \right] \geq (1 - \alpha) \cdot \mathbb{E}_{P_{\text{target}}}[h(X_{\text{test}})]$$

subject to the exchangeability of $(s(X_i, Y_i), r(X_i), h(X_i))_{i=1}^n$ under $P_{\text{source}}$.

## Interpretation

The guarantee is **harm-weighted coverage**: the test point is in the prediction set with probability at least $1 - \alpha$, *where the probability is weighted by the harm function*. High-harm strata (dosing, contraindication) get the coverage guarantee at the same $1 - \alpha$ level as the global split-CP guarantee, but the CALIBRATION AMOUNT spent on each stratum is proportional to the harm weight — more of the calibration budget goes to the categories where a miss costs more.

When $h \equiv 1$ the statement reduces to Tibshirani's weighted-CP guarantee (2019 Theorem 1). When $r \equiv 1$ (no shift) and the weights are grouped by stratum (via indicator functions of $h$) the statement reduces to a harm-stratified Mondrian-CP variant.

## Proof sketch (draft)

1. Under exchangeability of the score-weight triples, apply Tibshirani Theorem 1 to the probability measure $Q$ whose Radon-Nikodym derivative against $P_{\text{source}}$ is $r(x) \cdot h(x) / \mathbb{E}_{P_{\text{source}}}[r \cdot h]$.
2. The weighted quantile $\hat{q}_\alpha$ is exactly the $(1 - \alpha)$-quantile of the score distribution under $Q$.
3. By the weighted quantile's coverage guarantee, $Q(s(X_{\text{test}}, Y_{\text{test}}) \leq \hat{q}_\alpha) \geq 1 - \alpha$.
4. Translate back: $Q$'s event probability equals the harm-weighted expectation under $P_{\text{target}}$, giving the statement.

Full proof, with regularity conditions and a sharper $1/n$ rate characterisation, is work in progress.

## Open questions

- **Finite-sample vs. asymptotic.** Tibshirani 2019 uses a (n+1)-corrected empirical quantile for the finite-sample guarantee; does the harm-weighted version retain that correction? Conjecture: yes, with obvious modifications.
- **Estimated likelihood ratio.** In practice $r$ is estimated. Does the guarantee degrade gracefully to $(1 - \alpha - \epsilon)$ as a function of the ratio estimator's TV error? Open.
- **Stratum coverage ≥ global coverage?** Is there a clean condition under which per-stratum coverage exceeds $1 - \alpha$? Mondrian gives this for free when stratification aligns with the shift; harm-weighted may not.
