<!-- Synthetic/fictional white paper generated as test input for the literature comparison pipeline. Authors, institutions, data and citations are invented. -->

# A Segment-Level Expected Loss Framework for Unsecured Revolving Credit: The Cardinal Loss Rate Model (CLRM v4.2)

**R. Osei-Bonsu**, Quantitative Credit Analytics, Meridian Bancorp
**T. Halvorsen**, Model Development, Meridian Bancorp
**P. Iyengar**, Model Risk Management (reviewer of record), Meridian Bancorp

Working Paper MB-QCA-2024-07 · Version 4.2 · Approved for internal distribution

---

## Abstract

We document the specification, estimation and validation of the Cardinal Loss Rate Model (CLRM), the incumbent expected credit loss engine for Meridian Bancorp's unsecured credit card portfolio. CLRM decomposes the twelve-month portfolio loss rate into the classical product of probability of default (PD), exposure at default (EAD) and loss given default (LGD), estimated at the level of 48 homogeneous risk segments defined by a cross of behaviour score band, utilization band and delinquency stage. PD is estimated with a segment-conditional logistic regression on a quarterly cohort panel spanning 2009Q1–2023Q4; EAD is estimated through a credit conversion factor (CCF) applied to undrawn commitments; LGD is estimated as one minus a beta-regression recovery rate on post-charge-off cash collections. On a holdout period covering 2021Q1–2023Q4 the model reproduces the realized annualized net loss rate of 3.41% with an absolute error of 14 basis points, and achieves a segment-level Gini coefficient of 0.612 on the twelve-month default indicator. We argue that the transparency and stability of a segment-level multiplicative decomposition outweigh the modest discriminatory gains available from account-level machine learning alternatives, and we provide the sensitivity analysis required to support that claim.

**Keywords:** expected credit loss, credit cards, probability of default, exposure at default, loss given default, credit conversion factor, loss rate

**JEL:** G21, G28, C25

---

## 1. Introduction

Unsecured revolving credit remains the most loss-intensive major asset class on the balance sheet of a diversified retail bank. Unlike a term loan, a credit card account has no contractual amortization schedule, a borrower-controlled drawdown option, and a balance that can grow materially in the months immediately preceding default. Any credible loss forecasting framework for the asset class must therefore model not only *whether* an account defaults but also *how much* is owed when it does and *how little* is recovered afterwards.

The regulatory and accounting literature has converged on a multiplicative decomposition of expected loss,

$$EL = PD \times EAD \times LGD,$$

which we adopt without modification. The contribution of this paper is not the decomposition itself but the disciplined treatment of each factor for a revolving retail portfolio, and the demonstration that a segment-level implementation is sufficient for the uses to which the model is put: allowance estimation under CECL, loss forecasting in the annual capital plan, and portfolio-level pricing floors.

Three design commitments distinguish CLRM from the alternatives reviewed in Section 2.

1. **Segment-level estimation.** The unit of observation is a (segment, cohort) cell rather than an account-month. Segments are defined ex ante from variables that the business already uses to manage the portfolio, so that every model output can be traced to a population a line-of-business owner recognizes.
2. **Discrete annual horizon with cohort stacking.** PD is estimated on twelve-month cohorts rather than on a monthly hazard. This sacrifices timing resolution in exchange for a direct, auditable mapping between the estimation target and the reported twelve-month loss rate.
3. **Separable factor estimation.** PD, EAD and LGD are estimated independently and combined multiplicatively. Correlation between factors is handled through an explicit stress overlay (Section 4.5) rather than through a joint likelihood.

Section 2 situates the model in the literature. Section 3 describes the data and the segmentation scheme. Section 4 gives the specification of each factor. Section 5 reports estimation results, Section 6 the validation evidence, and Section 7 the limitations that motivate the challenger program.

---

## 2. Related Work

Three strands of work bear on the specification choices made here.

**Scorecard-based PD estimation.** The retail credit scoring tradition established by Altman (1968) and extended to behavioural data by Thomas (2000) treats default as a binary outcome predicted from a linear index of borrower attributes. Delacroix and Whitmore (2011) show that for revolving products the marginal predictive content of behavioural variables beyond a lagged delinquency stage and a utilization ratio is small at a twelve-month horizon, a result we replicate in Section 5.1. Marchetti (2016) documents that logistic scorecards estimated on segment aggregates retain 92–96% of the discriminatory power of the account-level equivalents when segments are defined on the score itself.

**Exposure measurement for committed revolving lines.** The CCF construct originates in the corporate revolver literature (Zhou and Aaltonen, 2009) and was adapted to cards by Ferreira-Lopes (2014), who documents the characteristic "run-up" pattern in which utilization rises from roughly 0.6 to above 0.95 in the six months preceding charge-off. Our treatment follows Ferreira-Lopes closely, with the modification that we cap the fitted CCF at unity to avoid predicting exposures above the contractual limit plus accrued fees.

**Recovery modelling on charged-off unsecured debt.** Recovery on unsecured retail debt arrives as a long, thin tail of collections and debt-sale proceeds. Brakefield and Sotomayor (2013) propose a beta regression on the ultimate recovery rate, censoring at a 36-month collection window; Nwosu (2019) argues for a discounted cash-flow treatment instead. We follow Brakefield and Sotomayor for the incumbent model and note in Section 7 that the discounting question is the single largest unresolved specification issue.

What the literature does not settle, and what motivated the present version, is the appropriate level of aggregation. Kessler, Duan and Rahimi (2020) find account-level gradient boosted models outperform segment scorecards by 4–7 Gini points on twelve-month card default, but also report a 2.3× increase in month-over-month forecast volatility. Our position is that for allowance and capital-planning uses, forecast stability is the binding constraint.

---

## 3. Data

### 3.1 Portfolio description

The estimation sample is the general-purpose credit card book of Meridian Bancorp, excluding the private-label co-brand partnerships (which are modelled separately) and excluding small-business cards. Table 1 summarizes the portfolio as of the final estimation quarter.

**Table 1. Portfolio composition, 2023Q4**

| Measure | Value |
|---|---|
| Active accounts | 7,412,880 |
| Outstanding balances | $28.6bn |
| Committed credit lines | $96.2bn |
| Aggregate utilization | 29.7% |
| Weighted-average behaviour score | 712 |
| Accounts 30+ days past due | 3.1% |
| Trailing 12-month gross charge-off rate | 4.02% |
| Trailing 12-month net charge-off rate | 3.41% |

### 3.2 Segmentation scheme

CLRM partitions the portfolio into 48 segments formed by the cross of:

- **Behaviour score band** (6 levels): <620, 620–659, 660–699, 700–739, 740–779, 780+
- **Utilization band** (4 levels): 0–25%, 25–60%, 60–90%, >90%
- **Delinquency stage** (2 levels at origin of cohort): current, 1–29 days past due

Accounts 30 or more days past due at cohort origin are routed to a separate roll-rate treatment described in Appendix A and are excluded from the regression sample. The segmentation was refit in 2022 using a CHAID partition on the twelve-month default indicator and then manually rationalized to align band cutpoints with the collections strategy already in force.

### 3.3 Default definition

An account is treated as defaulted in a cohort if, within twelve months of cohort origin, any of the following occurs: (i) contractual charge-off at 180 days past due; (ii) bankruptcy charge-off; (iii) enrollment in a long-term hardship program with a contractual rate concession exceeding 500 basis points. Definition (iii) contributes 8.4% of defaults and was added in version 4.0 following a 2021 finding by Model Risk Management that hardship enrollments were materially under-captured.

Cohorts are formed quarterly, so the panel contains 60 quarterly cohorts × 48 segments = 2,880 cells, of which 2,844 exceed the 250-account minimum size threshold and enter estimation.

---

## 4. Methodology

### 4.1 Loss rate decomposition

Let $s$ index segments and $t$ index quarterly cohorts. Define the twelve-month loss rate for segment $s$ in cohort $t$ as the ratio of realized net credit losses to the beginning balance:

$$LR_{s,t} = \frac{\sum_{i \in s,t} D_{i} \cdot E_{i} \cdot (1 - R_{i})}{\sum_{i \in s,t} B_{i}},$$

where $D_i$ is the default indicator, $E_i$ the exposure at default, $R_i$ the ultimate recovery rate and $B_i$ the beginning balance. Taking expectations segment by segment and replacing the ratio of expectations with the product of factor estimates yields the working form of the model:

$$\widehat{LR}_{s,t} = \widehat{PD}_{s,t} \times \widehat{CCF}_{s} \times \frac{L_{s,t}}{B_{s,t}} \times \widehat{LGD}_{s},$$

where $L_{s,t}$ is the aggregate committed line and the ratio $L_{s,t}/B_{s,t}$ converts the exposure factor from a line basis to a balance basis. Portfolio loss rate is the balance-weighted sum across segments.

The replacement of $E[D \cdot E \cdot (1-R)]$ with $E[D] \cdot E[E] \cdot E[1-R]$ is exact only under factor independence. Section 6.3 quantifies the induced bias.

### 4.2 Probability of default

PD is estimated by pooled logistic regression on the cohort panel, with segment fixed effects and macroeconomic covariates:

$$\ln\left(\frac{PD_{s,t}}{1 - PD_{s,t}}\right) = \alpha_s + \beta_1 \Delta u_{t} + \beta_2 \, hpi_{t} + \beta_3 \, dsr_{t} + \beta_4 \, pay_{s,t} + \beta_5 \, \Delta util_{s,t} + \varepsilon_{s,t}$$

with covariates defined as follows:

| Symbol | Definition | Source |
|---|---|---|
| $\Delta u_t$ | Four-quarter change in national unemployment rate | BLS |
| $hpi_t$ | Four-quarter log change in national house price index | FHFA |
| $dsr_t$ | Household debt service ratio, level | Federal Reserve H.8 |
| $pay_{s,t}$ | Segment mean payment rate (payments ÷ beginning balance) | Internal |
| $\Delta util_{s,t}$ | Segment mean four-quarter change in utilization | Internal |

Observations are weighted by cell account count. The macro covariate set was selected by exhaustive search over a 14-variable candidate library subject to (i) sign consistency with credit intuition, (ii) pairwise correlation below 0.70, and (iii) variance inflation below 5. House price appreciation enters despite the unsecured nature of the product; Delacroix and Whitmore (2011) attribute this to a collateral-substitution channel whereby homeowners under stress draw on secured equity before revolving credit.

### 4.3 Exposure at default

For a revolving line, exposure at default is decomposed into drawn and undrawn components:

$$EAD_i = B_i + CCF_s \cdot (L_i - B_i).$$

$CCF_s$ is estimated as the ratio of realized additional drawdown to available line over the twelve months preceding charge-off, pooled within segment and winsorized at the 1st and 99th percentiles. The estimator is the *fixed-horizon* variant: for each defaulted account, the reference date is exactly twelve months before the charge-off date, and accounts whose line was reduced by the bank during the window are excluded to avoid attributing management action to borrower behaviour. This exclusion removes 11.2% of defaults and is a known conservatism: excluded accounts had a mean realized drawdown below the retained population.

CCF is capped at 1.00 and floored at 0.00. No macroeconomic conditioning is applied to CCF; a 2022 study found the through-the-cycle variation in segment CCF to be within the estimation standard error for all but the >90% utilization band.

### 4.4 Loss given default

LGD is modelled as one minus the ultimate recovery rate, where recovery is nominal cash collected within 36 months of charge-off, inclusive of debt-sale proceeds net of agency commissions:

$$R_i \in (0,1), \qquad R_i \sim \text{Beta}(\mu_i \phi, (1-\mu_i)\phi), \qquad \text{logit}(\mu_i) = \gamma_0 + \gamma_1 \, \text{chan}_i + \gamma_2 \ln EAD_i + \gamma_3 \, \text{bk}_i + \gamma_4 \, \text{stage}_i.$$

Covariates are the resolution channel (internal collections, agency placement, debt sale), log exposure at default, a bankruptcy flag, and the delinquency stage at charge-off. Recoveries are *not* discounted in the incumbent model; the nominal treatment is inherited from the pre-2015 regulatory reporting convention and is the subject of a standing finding (Section 7, item 3).

Segment LGD is the exposure-weighted mean of fitted account values. No macro conditioning is applied.

### 4.5 Aggregation and stress overlay

Portfolio loss rate is the balance-weighted aggregate of segment loss rates. Because the factors are estimated separately, the multiplicative form understates loss in stressed conditions, where PD, EAD and LGD deteriorate jointly. CLRM addresses this with an explicit overlay: under any scenario in which projected $\Delta u_t$ exceeds 200 basis points, segment LGD is increased by a scenario-specific additive factor $\lambda(\Delta u)$ calibrated to the 2009–2010 realized recovery shortfall, and CCF in the >90% utilization band is raised by 4 percentage points. The overlay is documented as a model adjustment rather than as an estimated parameter and is re-approved annually.

---

## 5. Model Estimation Results

### 5.1 PD estimates

**Table 2. Pooled logistic PD regression, 2009Q1–2020Q4 development sample**

| Variable | Coefficient | Std. error | t-stat |
|---|---|---|---|
| $\Delta u_t$ (unemployment change) | 0.1842 | 0.0211 | 8.73 |
| $hpi_t$ (log HPI change) | −1.0937 | 0.2604 | −4.20 |
| $dsr_t$ (debt service ratio) | 0.2715 | 0.0893 | 3.04 |
| $pay_{s,t}$ (payment rate) | −3.4021 | 0.4118 | −8.26 |
| $\Delta util_{s,t}$ (utilization change) | 2.1166 | 0.3072 | 6.89 |
| Segment fixed effects | 48 estimated | — | — |
| Pseudo-$R^2$ | 0.417 | | |
| Observations (cells) | 2,268 | | |

All coefficients carry the expected sign and are significant at the 1% level. The payment-rate coefficient is the largest in standardized terms, consistent with Marchetti (2016): borrowers who pay more than the minimum are dramatically less likely to default regardless of score band.

Adding a candidate set of 9 further behavioural variables (months on book, number of trades, inquiry counts, cash-advance share, and interactions) raised the development-sample Gini from 0.612 to 0.631 while reducing holdout Gini to 0.598. The parsimonious specification was retained.

### 5.2 CCF estimates

**Table 3. Estimated credit conversion factors by utilization band**

| Utilization band | CCF | 95% CI | Defaults in sample |
|---|---|---|---|
| 0–25% | 0.184 | [0.171, 0.197] | 41,208 |
| 25–60% | 0.327 | [0.311, 0.343] | 78,611 |
| 60–90% | 0.541 | [0.522, 0.560] | 112,945 |
| >90% | 0.806 | [0.781, 0.831] | 96,330 |

The monotone increase in CCF with utilization reproduces the run-up pattern of Ferreira-Lopes (2014). Note that the >90% band CCF of 0.806 applies to a small remaining undrawn amount, so its contribution to portfolio EAD is modest despite the large coefficient.

### 5.3 LGD estimates

**Table 4. Beta regression on ultimate recovery rate**

| Variable | Coefficient | Std. error |
|---|---|---|
| Intercept | −1.9104 | 0.0662 |
| Agency placement (vs. internal) | −0.4188 | 0.0241 |
| Debt sale (vs. internal) | −0.7733 | 0.0309 |
| $\ln EAD$ | −0.1526 | 0.0188 |
| Bankruptcy flag | −0.9014 | 0.0455 |
| Stage at charge-off (180+ vs. other) | −0.2107 | 0.0233 |
| Precision $\phi$ | 4.81 | 0.09 |

Implied portfolio LGD is 0.853, i.e. a mean ultimate recovery of 14.7 cents on the dollar. Bankruptcy charge-offs recover 5.1 cents; internally worked non-bankruptcy accounts recover 21.3 cents.

### 5.4 Assembled loss rate

**Table 5. Loss rate build-up, 2023Q4 portfolio, baseline scenario**

| Score band | Balance share | PD | EAD/Balance | LGD | Loss rate |
|---|---|---|---|---|---|
| <620 | 8.1% | 14.82% | 1.12 | 0.871 | 14.46% |
| 620–659 | 11.4% | 8.91% | 1.14 | 0.866 | 8.80% |
| 660–699 | 17.9% | 5.27% | 1.17 | 0.858 | 5.29% |
| 700–739 | 22.6% | 2.84% | 1.21 | 0.850 | 2.92% |
| 740–779 | 20.8% | 1.33% | 1.26 | 0.844 | 1.41% |
| 780+ | 19.2% | 0.51% | 1.34 | 0.836 | 0.57% |
| **Portfolio** | **100%** | **3.92%** | **1.22** | **0.851** | **4.07%** |

The EAD/balance ratio rises with score band because higher-score accounts carry larger undrawn commitments relative to balance. This partially offsets the PD gradient and is the main reason a PD-only loss proxy misprices the prime end of the book.

---

## 6. Validation

### 6.1 Discriminatory power

On the 2021Q1–2023Q4 holdout, the segment-level PD ranking achieves a Gini coefficient of 0.601 (development: 0.612) and a Kolmogorov–Smirnov statistic of 0.442. Degradation of 1.1 Gini points is within the 5-point tolerance in the bank's validation standard.

### 6.2 Calibration and backtest

**Table 6. Holdout backtest of annualized net loss rate**

| Period | Predicted | Realized | Error (bps) |
|---|---|---|---|
| 2021 | 2.29% | 2.11% | +18 |
| 2022 | 2.96% | 3.08% | −12 |
| 2023 | 3.58% | 3.41% | +17 |
| Mean absolute error | | | 14 |

A binomial test of predicted against realized default counts fails to reject calibration at the 5% level in 44 of 48 segments. The four failures are all in the <620 score band, where the model over-predicts default — a pattern attributable to the 2021–2022 period of unusually strong consumer liquidity.

### 6.3 Independence-assumption bias

To quantify the bias from factor separability, we computed the realized loss rate directly as $\sum D_i E_i (1-R_i) / \sum B_i$ and compared it to the product of realized factor means. The product form understates realized loss by 6 to 9 basis points in benign quarters and by 41 basis points in 2009Q4, the worst quarter in the sample. The stress overlay of Section 4.5 contributes 55 basis points at a 200 bps unemployment shock, so the overlay is conservative relative to the measured bias at that severity. We have not tested severities beyond the 2009 experience.

### 6.4 Sensitivity

A ±10% relative shock to each factor produces the following loss-rate elasticities: PD 1.00, CCF 0.18, LGD 1.00. Loss rate is thus far more sensitive to PD and LGD than to the exposure factor, which supports the decision not to macro-condition CCF.

---

## 7. Limitations and Known Findings

1. **No lifetime horizon.** CLRM produces a twelve-month loss rate. Lifetime expected credit loss for accounting purposes is derived by applying an externally specified multiple to the twelve-month output. This is an acknowledged weakness and the primary driver of the challenger program.
2. **Segment drift.** Segment definitions are refit on a multi-year cycle. Between refits, population shift within bands is monitored but not corrected. The population stability index on the behaviour score distribution reached 0.14 in 2023Q4, above the 0.10 warning threshold.
3. **Undiscounted recoveries.** Nominal treatment of collections overstates recovery value and therefore understates LGD. At a 6% discount rate and the observed collection timing profile, discounted LGD would be approximately 0.878 rather than 0.853, raising portfolio loss rate by roughly 12 basis points.
4. **CCF exclusion conservatism.** Excluding line-reduced accounts from CCF estimation is conservative in direction but of unquantified magnitude.
5. **Overlay rather than joint estimation.** Factor correlation is handled judgmentally. A jointly estimated alternative would be preferable if it could be made stable.

---

## 8. Conclusion

CLRM v4.2 delivers a twelve-month credit card loss rate that is accurate to within 20 basis points on holdout, decomposable into factors that line-of-business owners can interrogate, and stable enough to be used in allowance and capital planning without month-over-month reconciliation burden. Its principal weaknesses are its fixed twelve-month horizon, its reliance on judgmental overlays for factor correlation, and its nominal treatment of recoveries. We recommend continued use of CLRM as the production model while a lifetime, account-level challenger is developed and benchmarked against the validation evidence reported here.

---

## References

Altman, E. (1968). Financial ratios, discriminant analysis and the prediction of corporate bankruptcy. *Journal of Finance*, 23(4), 589–609.

Brakefield, D., and Sotomayor, L. (2013). Beta regression for recovery rates on charged-off unsecured consumer debt. *Journal of Credit Risk Modelling*, 9(2), 33–61.

Delacroix, H., and Whitmore, J. (2011). Behavioural predictors of revolving credit default at short horizons. *Review of Retail Finance*, 14(3), 201–229.

Ferreira-Lopes, A. (2014). Exposure run-up on committed revolving retail lines. *Quantitative Banking Studies*, 6(1), 77–104.

Kessler, M., Duan, Y., and Rahimi, S. (2020). Gradient boosting versus scorecards for card default: accuracy, stability and governance. *Journal of Applied Credit Analytics*, 12(4), 415–448.

Marchetti, G. (2016). Aggregation loss in segment-level retail credit scoring. *European Journal of Risk Measurement*, 19(2), 155–180.

Nwosu, C. (2019). Discounting post-default collections in unsecured retail portfolios. *Journal of Credit Risk Modelling*, 15(1), 1–24.

Thomas, L. (2000). A survey of credit and behavioural scoring. *International Journal of Forecasting*, 16(2), 149–172.

Zhou, K., and Aaltonen, R. (2009). Credit conversion factors for committed corporate facilities. *Banking and Capital Review*, 4(2), 121–149.

---

## Appendix A. Delinquent-Account Roll-Rate Treatment

Accounts 30 or more days past due at cohort origin are excluded from the logistic PD regression and assigned a PD from an empirical roll-rate matrix estimated on trailing eight quarters. The matrix gives the probability of migrating from each delinquency bucket to charge-off within twelve months:

| Stage at origin | P(charge-off within 12m) |
|---|---|
| 30–59 DPD | 0.384 |
| 60–89 DPD | 0.617 |
| 90–119 DPD | 0.821 |
| 120–149 DPD | 0.918 |
| 150–179 DPD | 0.971 |

EAD for these accounts uses a CCF of 0.90 uniformly, reflecting that lines are typically blocked at 60 DPD. LGD uses the segment estimate from Section 4.4 without modification.

## Appendix B. Variable Dictionary

| Field | Definition |
|---|---|
| Beginning balance $B_i$ | Statement balance at cohort origin, excluding accrued unbilled interest |
| Committed line $L_i$ | Contractual credit limit at cohort origin |
| Payment rate | Trailing three-month mean of payments received divided by beginning balance |
| Utilization | Beginning balance divided by committed line, capped at 1.50 |
| Behaviour score | Internal score, refreshed monthly, 350–850 range |
| Ultimate recovery | Cash collected in 36 months post charge-off plus net debt-sale proceeds, divided by EAD |
