SELECT
  billing_date,
  ROUND(SUM(cost), 2) AS daily_spend
FROM fact_cloud_costs
GROUP BY billing_date
ORDER BY billing_date;
