-- Cumulative revenue per install (ARPI = LTV to date) by channel and day N,
-- restricted to cohorts old enough to have reached day N.
WITH params AS (SELECT DATE '2025-09-30' AS obs_end),
eligible AS (   -- players observed for at least N days, for each N we report
    SELECT p.player_id, p.channel, d.day_n
    FROM players p
    CROSS JOIN (SELECT UNNEST([0, 1, 3, 7, 14, 30, 60, 90]) AS day_n) d
    CROSS JOIN params
    WHERE p.install_date + d.day_n * INTERVAL 1 DAY <= params.obs_end
),
rev AS (
    SELECT e.channel, e.day_n, e.player_id,
           COALESCE(SUM(a.iap_revenue_eur + a.ad_revenue_eur), 0) AS revenue_to_day
    FROM eligible e
    LEFT JOIN daily_activity a
           ON a.player_id = e.player_id AND a.day_n <= e.day_n
    GROUP BY e.channel, e.day_n, e.player_id
)
SELECT channel, day_n,
       COUNT(*) AS players_observed,
       ROUND(AVG(revenue_to_day), 4) AS cumulative_arpi_eur
FROM rev
GROUP BY channel, day_n
ORDER BY channel, day_n;
