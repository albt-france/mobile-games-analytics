-- Paid channels: spend, installs, CPI and ROAS at day 7 / 30 / 90 on cohorts installed Jan-Mar 2025
-- (old enough to be observed for 90+ days by the 2025-09-30 cut-off).
WITH cohort AS (
    SELECT * FROM players
    WHERE install_date BETWEEN DATE '2025-01-01' AND DATE '2025-03-31' AND channel <> 'Organic'
),
spend AS (
    SELECT channel, SUM(spend_eur) AS spend_eur, SUM(installs) AS paid_installs
    FROM ua_spend
    WHERE date BETWEEN DATE '2025-01-01' AND DATE '2025-03-31'
    GROUP BY channel
),
rev AS (
    SELECT c.channel,
           SUM(CASE WHEN a.day_n <= 7  THEN a.iap_revenue_eur + a.ad_revenue_eur ELSE 0 END) AS rev_d7,
           SUM(CASE WHEN a.day_n <= 30 THEN a.iap_revenue_eur + a.ad_revenue_eur ELSE 0 END) AS rev_d30,
           SUM(CASE WHEN a.day_n <= 90 THEN a.iap_revenue_eur + a.ad_revenue_eur ELSE 0 END) AS rev_d90
    FROM cohort c
    JOIN daily_activity a USING (player_id)
    GROUP BY c.channel
)
SELECT s.channel, s.paid_installs,
       ROUND(s.spend_eur, 0)                    AS spend_eur,
       ROUND(s.spend_eur / s.paid_installs, 2)  AS cpi_eur,
       ROUND(r.rev_d7  / s.spend_eur, 3)        AS roas_d7,
       ROUND(r.rev_d30 / s.spend_eur, 3)        AS roas_d30,
       ROUND(r.rev_d90 / s.spend_eur, 3)        AS roas_d90
FROM spend s
JOIN rev r USING (channel)
ORDER BY roas_d90 DESC;
