SELECT
    billing_month,
    monthly_spend,
    previous_month_spend,
    mom_change,
    mom_change_percent
FROM monthly_spend_summary
ORDER BY billing_month;
