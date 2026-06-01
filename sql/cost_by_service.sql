SELECT
  service,
  ROUND(SUM(cost), 2) AS total_spend,
  ROUND(100.0 * SUM(cost) / SUM(SUM(cost)) OVER (), 2) AS percent_of_total
FROM fact_cloud_costs
GROUP BY service
ORDER BY total_spend DESC;
