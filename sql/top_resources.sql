SELECT
  resource_id,
  service,
  team,
  project,
  environment,
  ROUND(SUM(cost), 2) AS total_spend
FROM fact_cloud_costs
GROUP BY resource_id, service, team, project, environment
ORDER BY total_spend DESC
LIMIT 10;
