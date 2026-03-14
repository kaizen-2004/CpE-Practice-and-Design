# Statistical Treatment for ISO/IEC 25010 User Evaluation

## Statistical Tools and Methods

The study uses both descriptive and inferential statistics to evaluate user perception of the prototype based on ISO/IEC 25010 quality characteristics.

### 1) Descriptive Statistics

For each survey item and each ISO characteristic, compute:

- Frequency (`f`) and percentage (`%`) of responses per rating level (1 to 5)
- Weighted mean (`WM`)
- Standard deviation (`SD`)

The weighted mean is computed as:

```
WM = (Σ f x) / N
```

Where:

- `f` = frequency of each response
- `x` = Likert score (1 to 5)
- `N` = total number of respondents

Interpret the mean using this verbal scale:

- `4.21 - 5.00` = Very High
- `3.41 - 4.20` = High
- `2.61 - 3.40` = Moderate
- `1.81 - 2.60` = Low
- `1.00 - 1.80` = Very Low

### 2) Inferential Statistics (Chi-Square)

To address differences in evaluation across respondent groups, apply a chi-square test.

Recommended test:

- **Chi-Square Test of Independence** to determine whether response category is associated with respondent group.

Steps:

1. Recode Likert responses into:
   - Positive (`4-5`)
   - Neutral (`3`)
   - Negative (`1-2`)
2. Build a contingency table: respondent group x response category.
3. Set significance level at `alpha = 0.05`.
4. State hypotheses:
   - `H0`: There is no significant association between respondent group and rating category.
   - `H1`: There is a significant association between respondent group and rating category.
5. Decision rule:
   - If `p <= 0.05`, reject `H0`.
   - If `p > 0.05`, fail to reject `H0`.

If expected counts are too small in multiple cells, combine sparse categories or use Fisher's exact test.

## Suggested Reporting Format

Report results in this order:

1. Item-level and characteristic-level `WM` and `SD`
2. Overall ISO 25010 mean
3. Chi-square results (`chi-square value`, `df`, `p-value`)
4. Interpretation in plain language linked to system acceptability

## Chapter-Ready Paragraph

The user evaluation data were analyzed using descriptive and inferential statistics. Descriptive statistics included frequency, percentage, weighted mean, and standard deviation for each ISO/IEC 25010 survey item and for each quality characteristic: functional suitability, performance efficiency, compatibility, usability, reliability, security, maintainability, and portability. A five-point Likert scale was used (`5` = Strongly Agree to `1` = Strongly Disagree). Mean scores were interpreted using predefined verbal descriptors. To determine whether evaluation patterns differed across respondent groups, a chi-square test of independence was applied to grouped response categories (positive, neutral, negative) at `alpha = 0.05`. The test results were used to identify whether respondent group was significantly associated with the distribution of system ratings.
