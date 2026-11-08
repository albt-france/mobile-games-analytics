-- Retention by install-week cohort and day N.
-- A cohort only counts day N once every player in it could have reached day N (no right-censoring bias).
WITH params AS (SELECT DATE '2025-09-30' AS obs_end),
cohorts AS (
    SELECT player_id, install_date, DATE_TRUNC('week', install_date) AS cohort_week
    FROM players
),
cohort_size AS (
    SELECT cohort_week, COUNT(*) AS installs, MAX(install_date) AS last_install
    FROM cohorts GROUP BY cohort_week
),
active AS (
    SELECT c.cohort_week, a.day_n, COUNT(DISTINCT a.player_id) AS active_players
    FROM daily_activity a
    JOIN cohorts c USING (player_id)
    WHERE a.day_n IN (1, 3, 7, 14, 30, 60, 90)
    GROUP BY c.cohort_week, a.day_n
)
SELECT s.cohort_week, s.installs, a.day_n,
       a.active_players,
       ROUND(a.active_players * 1.0 / s.installs, 4) AS retention
FROM cohort_size s
JOIN active a USING (cohort_week)
CROSS JOIN params p
WHERE s.last_install + a.day_n * INTERVAL 1 DAY <= p.obs_end     -- fully observed only
ORDER BY s.cohort_week, a.day_n;
