SELECT
  strftime('%Y-%m', billing_date) AS billing_month,
  ROUND(SUM(cost), 2) AS total_spend
FROM fact_cloud_costs
GROUP BY billing_month
ORDER BY billing_month;
