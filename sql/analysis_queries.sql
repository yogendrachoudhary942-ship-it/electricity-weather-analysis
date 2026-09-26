-- Analysis queries for the electricity_demand table (SQLite)
-- Run with: sqlite3 data/processed/psp.db < sql/analysis_queries.sql
-- or paste individual queries into any SQLite client.

-- All queries below use period_type = 'monthly' (not the cumulative_fy rows)
-- and exclude region/grand totals unless a query specifically wants them.


-- 1. National demand trend over time (state-level rows summed per month)
SELECT
    year,
    month,
    ROUND(SUM(requirement_mu), 0) AS total_requirement_mu,
    ROUND(SUM(supplied_mu), 0) AS total_supplied_mu
FROM electricity_demand
WHERE period_type = 'monthly'
  AND is_region_total = 0
  AND is_grand_total = 0
GROUP BY year, month
ORDER BY year, month;


-- 2. Top 15 highest-deficit months by state (biggest shortfalls, MU)
SELECT
    state, year, month, month_name,
    requirement_mu, supplied_mu, deficit_mu, deficit_pct
FROM electricity_demand
WHERE period_type = 'monthly'
  AND is_region_total = 0
  AND is_grand_total = 0
  AND deficit_mu IS NOT NULL
ORDER BY deficit_mu DESC
LIMIT 15;


-- 3. Seasonal pattern: average national demand by calendar month, across all years
--    (reveals summer AC-load peaks vs monsoon dips vs winter patterns)
SELECT
    month,
    month_name,
    ROUND(AVG(monthly_total), 0) AS avg_requirement_mu
FROM (
    SELECT year, month, month_name, SUM(requirement_mu) AS monthly_total
    FROM electricity_demand
    WHERE period_type = 'monthly'
      AND is_region_total = 0
      AND is_grand_total = 0
    GROUP BY year, month, month_name
)
GROUP BY month, month_name
ORDER BY month;


-- 4. Year-over-year growth: national requirement by year (April fiscal-year proxy)
SELECT
    year,
    ROUND(SUM(requirement_mu), 0) AS total_requirement_mu,
    ROUND(
        100.0 * (SUM(requirement_mu) - LAG(SUM(requirement_mu)) OVER (ORDER BY year))
        / LAG(SUM(requirement_mu)) OVER (ORDER BY year),
        2
    ) AS pct_growth_vs_prev_year
FROM electricity_demand
WHERE period_type = 'monthly'
  AND is_region_total = 0
  AND is_grand_total = 0
GROUP BY year
ORDER BY year;


-- 5. Which states have the most volatile deficits? (highest std-dev of deficit %
--    across all their monthly records — flags states with inconsistent supply)
SELECT
    state,
    COUNT(*) AS months_recorded,
    ROUND(AVG(deficit_pct), 2) AS avg_deficit_pct,
    ROUND(
        SQRT(AVG(deficit_pct * deficit_pct) - AVG(deficit_pct) * AVG(deficit_pct)),
        2
    ) AS stddev_deficit_pct
FROM electricity_demand
WHERE period_type = 'monthly'
  AND is_region_total = 0
  AND is_grand_total = 0
  AND deficit_pct IS NOT NULL
GROUP BY state
HAVING months_recorded > 12
ORDER BY stddev_deficit_pct DESC
LIMIT 15;


-- 6. Regional totals over time (Northern/Western/Southern/Eastern/NE Region rows)
--    Useful for comparing regions directly rather than 36 individual states.
SELECT
    state AS region,
    year,
    ROUND(SUM(requirement_mu), 0) AS total_requirement_mu,
    ROUND(SUM(deficit_mu), 0) AS total_deficit_mu
FROM electricity_demand
WHERE period_type = 'monthly'
  AND is_region_total = 1
GROUP BY state, year
ORDER BY state, year;


-- 7. Single-state deep dive (swap the state name to explore any state)
--    Example here: Maharashtra's full monthly time series.
SELECT year, month, month_name, requirement_mu, supplied_mu, deficit_mu, deficit_pct
FROM electricity_demand
WHERE period_type = 'monthly'
  AND state = 'Maharashtra'
ORDER BY year, month;
