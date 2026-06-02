SELECT
    billing_month,
    team,
    actual_spend,
    monthly_budget,
    variance,
    budget_used_percent,
    status
FROM team_budget_variance
ORDER BY billing_month DESC, variance DESC;
