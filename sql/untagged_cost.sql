SELECT
  team,
  project,
  environment,
  ROUND(SUM(cost), 2) AS unallocated_spend
FROM fact_cloud_costs
WHERE is_unallocated = 1
GROUP BY team, project, environment
ORDER BY unallocated_spend DESC;
