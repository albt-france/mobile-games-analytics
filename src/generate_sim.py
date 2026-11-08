"""Simulated player-level UA & monetization data for a casual mobile puzzle game.

Calibrated on public benchmarks (see data/SOURCES.md). NOT real Rovio data.
Outputs (data/clean):
  sim_players.csv        one row per install (player_id, install_date, channel, country, platform)
  sim_daily_activity.csv one row per player-day active (player_id, activity_date, day_n, iap_revenue_eur, ad_revenue_eur)
  sim_ua_spend.csv       daily spend and paid installs by channel and country
"""
import numpy as np, pandas as pd

rng = np.random.default_rng(42)
INSTALL_START, INSTALL_END = pd.Timestamp("2025-01-01"), pd.Timestamp("2025-06-30")
OBS_END = pd.Timestamp("2025-09-30")          # data cut-off: later cohorts are only partly observed
INSTALLS_PER_DAY = 400
MAX_DAY = 180

# channel: share of installs, CPI (EUR, US-equivalent), retention and payer multipliers
CHANNELS = {
    "Organic":   dict(share=0.30, cpi=0.0, ret=1.10, pay=1.10),
    "Google":    dict(share=0.20, cpi=2.6, ret=1.00, pay=1.05),
    "Meta":      dict(share=0.18, cpi=3.0, ret=0.95, pay=1.00),
    "AppLovin":  dict(share=0.14, cpi=3.6, ret=1.05, pay=1.35),
    "Unity Ads": dict(share=0.10, cpi=2.2, ret=0.90, pay=0.85),
    "TikTok":    dict(share=0.08, cpi=1.7, ret=0.80, pay=0.60),
}
# country: share of installs, cost multiplier, revenue multiplier
COUNTRIES = {
    "US": dict(share=0.32, cost=1.60, rev=1.60), "DE": dict(share=0.10, cost=1.10, rev=1.10),
    "GB": dict(share=0.08, cost=1.10, rev=1.10), "FR": dict(share=0.08, cost=0.90, rev=0.95),
    "JP": dict(share=0.07, cost=1.40, rev=1.50), "BR": dict(share=0.13, cost=0.30, rev=0.30),
    "IN": dict(share=0.10, cost=0.15, rev=0.12), "Other": dict(share=0.12, cost=0.50, rev=0.50),
}
PLATFORMS = {"iOS": dict(share=0.45, rev=1.35), "Android": dict(share=0.55, rev=0.75)}

# retention backbone: P(active on day n) = A * n^-B, D1 ~ 44%, D7 ~ 19% (Cookie Cats)
A, B = 0.445, 0.435
P_ACTIVE_WHILE_ALIVE = 0.70        # an alive player does not open the game every day
BASE_PAYER_RATE = 0.022            # share of installs who ever pay (before multipliers)
PRICE_POINTS = np.array([1.99, 4.99, 9.99, 19.99, 49.99])
PRICE_WEIGHTS = np.array([0.34, 0.30, 0.20, 0.11, 0.05])
P_PURCHASE_PER_ACTIVE_DAY = 0.28   # for payers
AD_REV_PER_ACTIVE_DAY = 0.026      # EUR, before country/platform multipliers

def pick(d, n):
    keys = list(d); p = np.array([d[k]["share"] for k in keys]); p = p / p.sum()
    return rng.choice(keys, size=n, p=p)

dates = pd.date_range(INSTALL_START, INSTALL_END, freq="D")
n_per_day = rng.poisson(INSTALLS_PER_DAY * (1 + 0.15 * np.sin(np.arange(len(dates)) / 9)), len(dates))
install_date = np.repeat(dates.values, n_per_day)
N = len(install_date)
players = pd.DataFrame({
    "player_id": np.arange(1, N + 1),
    "install_date": pd.to_datetime(install_date),
    "channel": pick(CHANNELS, N),
    "country": pick(COUNTRIES, N),
    "platform": pick(PLATFORMS, N),
})
ch_ret = players.channel.map({k: v["ret"] for k, v in CHANNELS.items()}).values
ch_pay = players.channel.map({k: v["pay"] for k, v in CHANNELS.items()}).values
co_rev = players.country.map({k: v["rev"] for k, v in COUNTRIES.items()}).values
pl_rev = players.platform.map({k: v["rev"] for k, v in PLATFORMS.items()}).values

# player engagement: lognormal around the channel multiplier
engage = ch_ret * rng.lognormal(0, 0.35, N)
payer = rng.random(N) < np.clip(BASE_PAYER_RATE * ch_pay * np.sqrt(co_rev) * engage, 0, 0.5)
engage = np.where(payer, engage * 1.35, engage)   # payers stay longer

# survival: alive on day n while U < S(n), with S(n) = A n^-B / P_ACTIVE, scaled by engagement
u = rng.random(N)
rows = []
obs_days = (OBS_END - players.install_date).dt.days.values
for n in range(1, MAX_DAY + 1):
    s = np.clip(A * n ** (-B) / P_ACTIVE_WHILE_ALIVE * engage, 0, 1)
    alive = u < s
    active = alive & (rng.random(N) < P_ACTIVE_WHILE_ALIVE) & (obs_days >= n)
    idx = np.nonzero(active)[0]
    if len(idx) == 0:
        continue
    buy = payer[idx] & (rng.random(len(idx)) < P_PURCHASE_PER_ACTIVE_DAY)
    iap = np.where(buy, rng.choice(PRICE_POINTS, size=len(idx), p=PRICE_WEIGHTS), 0.0) * np.sqrt(co_rev[idx])
    ads = AD_REV_PER_ACTIVE_DAY * co_rev[idx] * pl_rev[idx] * rng.gamma(2.0, 0.5, len(idx))
    ads = np.where(payer[idx], ads * 0.6, ads)   # payers often remove ads
    rows.append(pd.DataFrame({"player_id": players.player_id.values[idx], "day_n": n,
                              "iap_revenue_eur": iap.round(2), "ad_revenue_eur": ads.round(4)}))
# day 0 (install day): everyone active
ads0 = AD_REV_PER_ACTIVE_DAY * co_rev * pl_rev * rng.gamma(2.0, 0.5, N)
buy0 = payer & (rng.random(N) < 0.25)
iap0 = np.where(buy0, rng.choice(PRICE_POINTS, size=N, p=PRICE_WEIGHTS), 0.0) * np.sqrt(co_rev)
rows.insert(0, pd.DataFrame({"player_id": players.player_id.values, "day_n": 0,
                             "iap_revenue_eur": iap0.round(2), "ad_revenue_eur": ads0.round(4)}))
act = pd.concat(rows, ignore_index=True)
act = act.merge(players[["player_id", "install_date"]], on="player_id")
act["activity_date"] = act.install_date + pd.to_timedelta(act.day_n, unit="D")
act = act[["player_id", "activity_date", "day_n", "iap_revenue_eur", "ad_revenue_eur"]].sort_values(["activity_date", "player_id"])

# UA spend: paid installs x CPI x country cost multiplier, with daily noise
paid = players[players.channel != "Organic"]
spend = paid.groupby(["install_date", "channel", "country"]).size().rename("installs").reset_index()
cpi = spend.channel.map({k: v["cpi"] for k, v in CHANNELS.items()}) * spend.country.map({k: v["cost"] for k, v in COUNTRIES.items()})
spend["spend_eur"] = (spend.installs * cpi * rng.normal(1, 0.08, len(spend))).round(2)
spend = spend.rename(columns={"install_date": "date"})

players.to_csv("data/clean/sim_players.csv", index=False, date_format="%Y-%m-%d")
act.to_csv("data/clean/sim_daily_activity.csv", index=False, date_format="%Y-%m-%d")
spend.to_csv("data/clean/sim_ua_spend.csv", index=False, date_format="%Y-%m-%d")

# calibration check
dau = act.groupby("activity_date").agg(dau=("player_id", "nunique"), rev=("iap_revenue_eur", "sum"), ads=("ad_revenue_eur", "sum"))
steady = dau.loc["2025-05-01":"2025-06-30"]
ret = act[act.day_n.isin([1, 7, 30])].groupby("day_n").player_id.nunique() / N
print(f"players {N:,}  activity rows {len(act):,}  paid spend EUR {spend.spend_eur.sum():,.0f}")
print("retention D1/D7/D30:", ret.round(3).to_dict())
print("ARPDAU (May-Jun):", round(((steady.rev + steady.ads).sum() / steady.dau.sum()), 3),
      " ad share:", round(steady.ads.sum() / (steady.rev + steady.ads).sum(), 2))
print("payer share of installs:", round(payer.mean(), 4))
