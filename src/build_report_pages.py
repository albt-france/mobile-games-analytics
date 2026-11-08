"""Generate the Power BI report pages (PBIR format) for powerbi/RovioCaseStudy.Report.

Usage:  python src/build_report_pages.py powerbi/RovioCaseStudy.Report
Close Power BI Desktop first (or let it reload): every page is rewritten from this script.
"""
import json, shutil, sys
from pathlib import Path

REPORT = Path(sys.argv[1])  # ...\RovioCaseStudy.Report
PAGES = REPORT / "definition" / "pages"
VC_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json"
PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.1.0/schema.json"
M = "_Measures"

# ink & palette (validated reference palette, light mode)
INK, INK2, MUTED = "#0B0B0B", "#52514E", "#898781"
BLUE = "#2A78D6"
SEQ = {"100": "#CDE2FB", "250": "#86B6EF", "350": "#5598E7", "450": "#2A78D6", "650": "#104281"}
NEUTRAL, RED_TINT, BLUE_TINT = "#F0EFEC", "#F4C7C6", "#B7D3F6"
AUTHOR = "Independent Data Analyst case study · Not affiliated with Rovio"


# ---------- expression helpers ----------
def raw(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"Literal": {"Value": s}}

def lit(v):
    return {"expr": raw(v)}

def color(hexv):
    return {"solid": {"color": lit(hexv)}}

def col(table, column):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}

def meas(name):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": M}}, "Property": name}}

def agg_sum(table, column):
    return {"Aggregation": {"Expression": col(table, column), "Function": 0}}

def qref(field):
    if "Column" in field:
        c = field["Column"]
        return f'{c["Expression"]["SourceRef"]["Entity"]}.{c["Property"]}'
    if "Measure" in field:
        return f'{M}.{field["Measure"]["Property"]}'
    c = field["Aggregation"]["Expression"]["Column"]
    return f'Sum({c["Expression"]["SourceRef"]["Entity"]}.{c["Property"]})'

def proj(field, label=None):
    p = {"field": field, "queryRef": qref(field)}
    if "Column" in field:
        p["nativeQueryRef"] = field["Column"]["Property"]
    elif "Measure" in field:
        p["nativeQueryRef"] = field["Measure"]["Property"]
    else:
        p["nativeQueryRef"] = "Sum of " + field["Aggregation"]["Expression"]["Column"]["Property"]
        p["displayName"] = field["Aggregation"]["Expression"]["Column"]["Property"]
    if label:
        p["displayName"] = label
    return p

def C(t, c): return col(t, c)
def Ms(*names): return [meas(n) for n in names]

def series_color(field, hexv):
    return {"properties": {"fill": color(hexv)}, "selector": {"metadata": qref(field)}}

def ref_line(value, label, hexv=INK2, selector_id="1"):
    v = {"expr": value} if isinstance(value, dict) else lit(value)
    return {"properties": {"show": lit(True), "value": v, "displayName": lit(label), "lineColor": color(hexv),
                           "style": lit("dashed"), "dataLabelShow": lit(True), "dataLabelColor": color(hexv)},
            "selector": {"id": selector_id}}

def bg_rule(field, lo, hi, mid=None, mid_value=None):
    """Background-colour scale (conditional formatting) on a table/matrix value column."""
    rule = {"min": {"color": raw(lo)}, "max": {"color": raw(hi)},
            "nullColoringStrategy": {"strategy": raw("asZero")}}
    key = "linearGradient2"
    if mid:
        key = "linearGradient3"
        rule["mid"] = {"color": raw(mid)}
        if mid_value is not None:
            rule["mid"]["value"] = raw(mid_value)
    return {"properties": {"backColor": {"solid": {"color": {"expr": {"FillRule": {"Input": field, "FillRule": {key: rule}}}}}}},
            "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": qref(field)}}


def table_style(extra_values=(), matrix=False):
    """Readable table: 12pt text, no misleading total row/column."""
    fs = {"properties": {"fontSize": lit(12)}}
    objs = {"values": [fs, *extra_values], "columnHeaders": [{"properties": {"fontSize": lit(12), "fontColor": color(INK2)}}]}
    if matrix:
        objs["rowHeaders"] = [fs]
        objs["subTotals"] = [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}]
    else:
        objs["total"] = [{"properties": {"totals": lit(False)}}]
    return objs


# ---------- page / visual builders ----------
class Page:
    def __init__(self, pid, name):
        self.pid, self.name, self.visuals, self.interactions, self.n = pid, name, [], [], 0

    def _add(self, vid, x, y, w, h, visual):
        self.n += 1
        self.visuals.append({"$schema": VC_SCHEMA, "name": vid,
                             "position": {"x": round(x), "y": round(y), "z": self.n * 1000,
                                          "height": round(h), "width": round(w), "tabOrder": self.n * 1000},
                             "visual": visual})
        return vid

    def chart(self, vid, vtype, x, y, w, h, roles, title=None, objects=None, labels=None,
              sort=None, exclude_organic=False, only=None):
        labels = labels or {}
        visual = {"visualType": vtype,
                  "query": {"queryState": {r: {"projections": [proj(f, labels.get(qref(f))) for f in fs]}
                                           for r, fs in roles.items() if fs}},
                  "drillFilterOtherVisuals": True}
        if sort:
            field, direction = sort
            visual["query"]["sortDefinition"] = {"sort": [{"field": field, "direction": direction}],
                                                 "isDefaultSort": False}
        if objects:
            visual["objects"] = objects
        vco = {"subTitle": [{"properties": {"show": lit(False)}}]}
        vco["title"] = [{"properties": {"show": lit(bool(title)), **({"text": lit(title)} if title else {})}}]
        visual["visualContainerObjects"] = vco
        vid = self._add(vid, x, y, w, h, visual)
        if exclude_organic:
            only = ("Channel", "channel", ["Organic"], True)
        if only:
            table, column, values, negate = only
            cond = {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": column}}],
                           "Values": [[raw(v)] for v in values]}}
            if negate:
                cond = {"Not": {"Expression": cond}}
            self.visuals[-1]["filterConfig"] = {"filters": [{
                "name": "visualFilter", "type": "Categorical", "field": col(table, column),
                "filter": {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}],
                           "Where": [{"Condition": cond}]}}]}
        return vid

    def text(self, vid, x, y, w, h, paragraphs, boxed=False):
        """paragraphs: list of paragraphs; each paragraph = list of (text, size, colour, bold) runs."""
        paras = [{"textRuns": [{"value": t, "textStyle": {"fontSize": f"{s}pt", "color": c,
                                                         **({"fontWeight": "bold"} if b else {})}}
                               for t, s, c, b in runs]} for runs in paragraphs]
        visual = {"visualType": "textbox",
                  "objects": {"general": [{"properties": {"paragraphs": paras}}]},
                  "visualContainerObjects": {"background": [{"properties": {"show": lit(boxed)}}],
                                             "border": [{"properties": {"show": lit(boxed)}}],
                                             **({"padding": [{"properties": {"top": lit(16), "bottom": lit(16),
                                                                             "left": lit(20), "right": lit(20)}}]}
                                                if boxed else {})}}
        return self._add(vid, x, y, w, h, visual)

    def header(self, title, conclusion, tag):
        self.text("title", 32, 20, 1500, 56, [[(title, 24, INK, True)]])
        self.text("tag", 1540, 28, 348, 40, [[(tag, 10, INK2, True)]])
        self.text("conclusion", 32, 76, 1856, 64, [[(conclusion, 13, INK2, False)]])

    def footer(self, source):
        self.text("footer", 32, 1040, 1856, 32, [[(source + "   ·   " + AUTHOR, 9, MUTED, False)]])

    def slicer(self, vid, x, y, w, h, field, title, dropdown=True, single=False):
        objs = {"header": [{"properties": {"show": lit(False)}}]}
        if dropdown:
            objs["data"] = [{"properties": {"mode": lit("Dropdown")}}]
        if single:
            objs["selection"] = [{"properties": {"singleSelect": lit(True), "strictSingleSelect": lit(True)}}]
        return self.chart(vid, "slicer", x, y, w, h, {"Values": [field]}, title, objs)

    def card(self, vid, x, y, w, h, measure, title, only=None):
        return self.chart(vid, "card", x, y, w, h, {"Values": [meas(measure)]}, title,
                          {"labels": [{"properties": {"color": color(INK), "fontSize": lit(28)}}],
                           "categoryLabels": [{"properties": {"show": lit(False)}}]}, only=only)

    def no_filter(self, source, target):
        self.interactions.append({"source": source, "target": target, "type": "NoFilter"})

    def write(self):
        d = PAGES / self.pid
        if d.exists():
            shutil.rmtree(d)
        (d / "visuals").mkdir(parents=True)
        page = {"$schema": PAGE_SCHEMA, "name": self.pid, "displayName": self.name,
                "displayOption": "FitToPage", "height": 1080, "width": 1920}
        if self.interactions:
            page["visualInteractions"] = self.interactions
        (d / "page.json").write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding="utf-8")
        for v in self.visuals:
            vd = d / "visuals" / v["name"]
            vd.mkdir()
            (vd / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- layout grid ----------
L, R, TOP, BOT, GAP = 32, 1888, 156, 1028, 24
W = R - L

def cols(n, x0=L, x1=R):
    w = (x1 - x0 - (n - 1) * GAP) / n
    return [(x0 + i * (w + GAP), w) for i in range(n)]

def kpi_row(p, items, y=TOP, h=120, x0=L, x1=R, only=None):
    for (x, w), (m, t) in zip(cols(len(items), x0, x1), items):
        p.card("kpi_" + "".join(ch for ch in m if ch.isalnum())[:30], x, y, w, h, m, t, only=only)
    return y + h + GAP

SRC_ROVIO = "Source: Rovio Entertainment interim reports & financial statements 2021-2022 (public)"
SRC_SIM = "Simulated player-level data (seed 42), illustrative only - not Rovio data"
SRC_CC = "Source: Cookie Cats mobile game A/B test, public dataset (90,189 players)"

pages = []

# ======================= Page 0 - Overview =======================
p = Page("e0a1b2c3d4e5f6a7b8c9", "Overview")
p.text("title", 32, 20, 1500, 56, [[("Mobile games analytics case study: UA, monetization, LTV", 24, INK, True)]])
p.text("tag", 1540, 28, 348, 40, [[("OVERVIEW", 10, INK2, True)]])
p.text("conclusion", 32, 76, 1856, 64, [[(
    "Five questions a UA, Ads & Portfolio analyst answers every week, worked end to end with SQL (DuckDB), "
    "Python (A/B test, LTV forecasting) and Power BI.", 13, INK2, False)]])
heroes = [("32%", "of Rovio's gross bookings went to user acquisition in 2022, up from 23% in 2020", "PUBLIC · PAGE 1"),
          ("Day 306", "AppLovin pays back its CPI; TikTok never does at its current CPI", "SIMULATED · PAGE 2"),
          ("< 6%", "error on day-90 LTV when forecasting from the first 30 days only", "SIMULATED · PAGE 4"),
          ("-0.8 pts", "D7 retention if the first gate moves from level 30 to 40 (p = 0.002)", "REAL · PAGE 5")]
hh = 250
for i, ((x, w), (num, txt, tag)) in enumerate(zip(cols(4), heroes)):
    p.text(f"hero{i+1}", x, TOP, w, hh, [[(tag, 10, INK2, True)], [(num, 44, INK, True)], [(txt, 15, INK2, False)]],
           boxed=True)
y2 = TOP + hh + GAP
(x1, w1), (x2, w2) = cols(2)
BH = 400
p.text("questions", x1, y2, w1, BH, [
    [("Business questions", 22, INK, True)],
    [("", 12, INK, False)],
    [("1 · Portfolio   ", 17, BLUE, True), ("How did Rovio grow bookings 2020-2022, and at what UA cost?", 17, INK, False)],
    [("2 · UA   ", 17, BLUE, True), ("Which acquisition channels pay back, and when?", 17, INK, False)],
    [("3 · Retention   ", 17, BLUE, True), ("How do cohorts retain, and where does revenue come from?", 17, INK, False)],
    [("4 · LTV   ", 17, BLUE, True), ("Can a channel be judged after 30 days instead of 90+?", 17, INK, False)],
    [("5 · A/B test   ", 17, BLUE, True), ("Should the first gate sit at level 30 or 40?", 17, INK, False)],
    [("", 12, INK, False)],
    [("Recommendation: ", 17, INK, True),
     ("shift UA budget toward AppLovin and Google, cap TikTok until its CPI drops below ~€0.93 (its 1-year LTV), "
      "review new channels at day 30, and keep the gate at level 30.", 17, INK2, False)],
], boxed=True)
p.text("data", x2, y2, w2, BH, [
    [("Data & methods", 22, INK, True)],
    [("", 12, INK, False)],
    [("PUBLIC   ", 14, INK2, True), ("Rovio quarterly KPIs and bookings by game, from published reports.", 17, INK, False)],
    [("SIMULATED   ", 14, INK2, True), ("Players, activity and UA spend generated in Python. Realistic patterns, not Rovio's numbers.", 17, INK, False)],
    [("REAL   ", 14, INK2, True), ("Cookie Cats A/B test, 90,189 players.", 17, INK, False)],
    [("", 12, INK, False)],
    [("SQL   ", 14, INK2, True), ("censoring-safe cohort retention, cumulative ARPI, ROAS by channel (DuckDB).", 17, INK, False)],
    [("Python   ", 14, INK2, True), ("z-test + bootstrap; power-curve LTV fit a·t^b with D30→D90 holdout; payback day.", 17, INK, False)],
    [("Power BI   ", 14, INK2, True), ("star schema, 30 DAX measures, one question per page.", 17, INK, False)],
], boxed=True)
y3 = y2 + BH + GAP
p.text("howto", L, y3, W, BOT - y3, [
    [("How to read this report", 17, INK, True)],
    [("Titles  ", 14, INK2, True), ("state the conclusion of the page.     ", 15, INK, False),
     ("Tags  ", 14, INK2, True), ("PUBLIC / SIMULATED / REAL mark where the data comes from.     ", 15, INK, False),
     ("Dashed lines  ", 14, INK2, True), ("mark break-even or a threshold.     ", 15, INK, False),
     ("Code  ", 14, INK2, True), ("SQL, Python notebook and Power BI project in the repository.", 15, INK, False)],
], boxed=True)
p.footer("Data sources listed in data/SOURCES.md")
pages.append(p)

# ======================= Page 1 - Rovio portfolio =======================
p = Page("102b38013016e5e859aa", "1 · Rovio portfolio")
p.header("Rovio portfolio: growth was bought, then monetized better",
         "UA rose from 23% of gross bookings in 2020 to 32% in 2022, while top-5 ARPDAU rose from €0.18 to €0.21 "
         "(annual figures). Dream Blast's Q4-22 record quarter came with the heaviest UA push.",
         "PUBLIC DATA")
y = kpi_row(p, [("Rovio Gross Bookings (EUR m)", "Gross bookings 2022 (EUR m)"),
                ("Rovio UA (EUR m)", "User acquisition 2022 (EUR m)"),
                ("Rovio UA Share", "UA share of gross bookings, 2022"),
                ("Rovio ARPDAU Top 5", "ARPDAU top-5 games, 2022 average")],
            only=("Rovio Quarterly", "quarter", ["2022Q1", "2022Q2", "2022Q3", "2022Q4"], False))
h = 380
p.chart("bookingsByGame", "columnChart", L, y, W, h,
        {"Category": [C("Rovio Games", "quarter")], "Y": [meas("Rovio Gross Bookings (EUR m)")],
         "Series": [C("Rovio Games", "game")]},
        "Gross bookings by game, EUR m (stacked)")
y += h + GAP
small = [("uaSpend", "clusteredColumnChart", "Rovio UA (EUR m)", "UA spend, EUR m"),
         ("uaShare", "lineChart", "Rovio UA Share", "UA as % of gross bookings"),
         ("arpdau", "lineChart", "Rovio ARPDAU Top 5", "ARPDAU top-5 games, EUR"),
         ("dau", "lineChart", "Rovio DAU Top 5 (m)", "DAU top-5 games, millions")]
for (x, w), (vid, vt, m, t) in zip(cols(4), small):
    p.chart(vid, vt, x, y, w, BOT - y, {"Category": [C("Rovio Quarterly", "quarter")], "Y": [meas(m)]}, t,
            {"dataPoint": [{"properties": {"fill": color(BLUE)}}],
             "legend": [{"properties": {"show": lit(False)}}]})
p.footer(SRC_ROVIO)
pages.append(p)

# ======================= Page 2 - UA performance =======================
p = Page("a2c0f1e3b4d5c6a7e8f9", "2 · UA performance")
p.header("AppLovin costs the most per install and pays back best; TikTok never pays back",
         "ROAS compares revenue generated by a channel's installs with what was spent to buy them. "
         "Above 100% the channel has paid for itself. AppLovin breaks even around day 306.",
         "SIMULATED DATA")
y = kpi_row(p, [("Total UA Spend", "Total UA spend"), ("Paid Installs", "Paid installs"),
                ("CPI", "Blended CPI"), ("ROAS D90", "ROAS D90 (spend-weighted)")])
h = 400
(xa, wa), (xb, wb) = cols(2)
roas = Ms("ROAS D7", "ROAS D30", "ROAS D90")
p.chart("roasByChannel", "clusteredColumnChart", xa, y, wa, h,
        {"Category": [C("Channel", "channel")], "Y": roas},
        "ROAS by channel at D7 / D30 / D90 (dashed = break-even)",
        {"dataPoint": [series_color(roas[0], SEQ["250"]), series_color(roas[1], SEQ["450"]),
                       series_color(roas[2], SEQ["650"])],
         "y1AxisReferenceLine": [ref_line(1, "Break-even 100%")]})
p.chart("cpiVsLtv", "scatterChart", xb, y, wb, h,
        {"Category": [C("Channel", "channel")], "X": [meas("CPI Line")], "Y": [meas("LTV D365")]},
        "CPI vs forecast 1-year LTV per install, EUR (above the diagonal: LTV > CPI, pays back within a year)",
        {"dataPoint": [{"properties": {"fill": color(BLUE)}}],
         "categoryLabels": [{"properties": {"show": lit(True), "color": color(INK2)}}],
         "markers": [{"properties": {"markerSize": lit(8)}}],
         "plotAreaShading": [{"properties": {"show": lit(True), "displayName": lit("Break-even diagonal"),
                                              "upperShadingColor": color(BLUE_TINT),
                                              "lowerShadingColor": color(RED_TINT), "transparency": lit(40)}}],
         "categoryAxis": [{"properties": {"start": lit(0), "end": lit(4.5)}}],
         "valueAxis": [{"properties": {"start": lit(0), "end": lit(4.5)}}]},
        labels={"_Measures.CPI Line": "CPI (EUR)", "_Measures.LTV D365": "LTV D365 forecast (EUR)"},
        exclude_organic=True)
y += h + GAP
tbl = [C("Channel", "channel")] + Ms("CPI", "ROAS D90", "ROAS D365 Forecast", "Payback Day")
p.chart("channelTable", "tableEx", xa, y, wa, BOT - y, {"Values": tbl},
        "Channel scorecard (red = below break-even, blue = above)",
        table_style([bg_rule(meas("ROAS D90"), RED_TINT, BLUE_TINT, NEUTRAL, 1),
                     bg_rule(meas("ROAS D365 Forecast"), RED_TINT, BLUE_TINT, NEUTRAL, 1)]),
        labels={"_Measures.Payback Day": "Payback day (forecast)", "Channel.channel": "Channel"},
        exclude_organic=True)
pb = meas("Payback Day")
p.chart("paybackBars", "clusteredBarChart", xb, y, wb, BOT - y,
        {"Category": [C("Channel", "channel")], "Y": [pb]},
        "Forecast payback day by channel (dashed = 1 year; TikTok never pays back)",
        {"dataPoint": [{"properties": {"fill": color(BLUE)}}],
         "labels": [{"properties": {"show": lit(True), "color": color(INK)}}],
         "y1AxisReferenceLine": [ref_line(365, "1 year")]},
        labels={qref(pb): "Payback day"}, sort=(pb, "Ascending"), exclude_organic=True)
p.footer(SRC_SIM)
pages.append(p)

# ======================= Page 3 - Retention & monetization =======================
p = Page("b3d1e2f4a5c6b7d8e9f0", "3 · Retention & monetization")
p.header("Retention falls from 47% at D1 to 21% at D7, then flattens; ads bring 23% of revenue",
         "Most churn happens in the first week (D30: 11%, D90: 7%), so early-game and onboarding changes have the biggest lever. "
         "Ads are a meaningful second revenue stream next to in-app purchases.",
         "SIMULATED DATA")
for (x, w), (f, t) in zip(cols(3), [(C("Channel", "channel"), "Channel"), (C("Country", "country"), "Country"),
                                    (C("Players", "platform"), "Platform")]):
    p.slicer("slicer_" + t, x, TOP, w, 72, f, t)
y = TOP + 72 + GAP
y = kpi_row(p, [("IAP Revenue", "IAP revenue"), ("Ad Revenue", "Ad revenue"),
                ("Ad Share", "Ad share of revenue"), ("Payer Conversion", "Payer conversion")], y=y, h=110)
left_w = W * 0.55
p.chart("cohortMatrix", "pivotTable", L, y, left_w, BOT - y,
        {"Rows": [C("Cohort Retention", "cohort_week")], "Columns": [C("Cohort Retention", "day_n")],
         "Values": [meas("Cohort Retention")]},
        "Cohort retention by install week and day N (all players, not filtered by slicers)",
        table_style([bg_rule(meas("Cohort Retention"), "#FCFCFB", SEQ["350"])], matrix=True),
        labels={"Cohort Retention.cohort_week": "Install week", "Cohort Retention.day_n": "Day"})
for tgt in ("cohortMatrix",):
    for s in ("slicer_Channel", "slicer_Country", "slicer_Platform"):
        p.no_filter(s, tgt)
rx = L + left_w + GAP
rh = (BOT - y - GAP) / 2
p.chart("dauMonthly", "clusteredColumnChart", rx, y, R - rx, rh,
        {"Category": [C("Date", "Month")], "Y": [meas("DAU")]}, "Average DAU by month (simulated installs stop on 30 June, so DAU declines from July)",
        {"dataPoint": [{"properties": {"fill": color(BLUE)}}]})
p.chart("arpdauMonthly", "lineChart", rx, y + rh + GAP, R - rx, rh,
        {"Category": [C("Date", "Month")], "Y": [meas("ARPDAU")]}, "ARPDAU by month, EUR (axis from 0)",
        {"dataPoint": [{"properties": {"fill": color(BLUE)}}],
         "valueAxis": [{"properties": {"start": lit(0)}}]})
p.footer(SRC_SIM)
pages.append(p)

# ======================= Page 4 - LTV forecast & payback =======================
p = Page("c4e2f3a5b6d7c8e9f0a1", "4 · LTV forecast & payback")
p.header("A 30-day fit predicts day-90 LTV within 6%: channels can be judged after one month",
         "LTV(t) = a·t^b fitted on days 0-30 for each channel, checked against the observed day-90 value (holdout). "
         "The channel breaks even on the day its LTV curve crosses its CPI.",
         "SIMULATED DATA")
h = 470
(xa, wa), (xb, wb) = cols(2)
p.chart("ltvAll", "lineChart", xa, TOP, wa, h,
        {"Category": [C("LTV Curves", "day_n")], "Y": [meas("LTV Forecast")], "Series": [C("LTV Curves", "channel")]},
        "Forecast cumulative LTV per install by channel, EUR")
sw = 240
p.slicer("slicerChannel", xb, TOP, sw, h, C("Channel", "channel"), "Pick one channel", dropdown=False, single=True)
fc, ob = meas("LTV Forecast"), meas("LTV Observed")
p.chart("ltvOne", "lineChart", xb + sw + GAP, TOP, R - (xb + sw + GAP), h,
        {"Category": [C("LTV Curves", "day_n")], "Y": [fc, ob]},
        "Selected channel: forecast (grey) vs observed (black) LTV, dashed = CPI",
        {"dataPoint": [series_color(fc, MUTED), series_color(ob, INK)],
         "y1AxisReferenceLine": [ref_line(meas("CPI Line"), "CPI")]},
        labels={"_Measures.LTV Forecast": "Forecast", "_Measures.LTV Observed": "Observed"})
for target in ("ltvAll", "forecastTable"):
    p.no_filter("slicerChannel", target)
y = TOP + h + GAP
ftab = [C("LTV Forecast", "channel"), agg_sum("LTV Forecast", "cpi_eur"), agg_sum("LTV Forecast", "ltv_d90_actual"),
        agg_sum("LTV Forecast", "ltv_d180_forecast"), agg_sum("LTV Forecast", "ltv_d365_forecast"),
        agg_sum("LTV Forecast", "holdout_d30_to_d90_error")]
p.chart("forecastTable", "tableEx", L, y, W, BOT - y, {"Values": ftab},
        "Forecast by paid channel (holdout error = fit on D0-30 vs actual D90)", table_style(),
        exclude_organic=True,
        labels={"LTV Forecast.channel": "Channel", "Sum(LTV Forecast.cpi_eur)": "CPI (EUR)", "Sum(LTV Forecast.ltv_d90_actual)": "LTV D90 actual",
                "Sum(LTV Forecast.ltv_d180_forecast)": "LTV D180 forecast",
                "Sum(LTV Forecast.ltv_d365_forecast)": "LTV D365 forecast",
                "Sum(LTV Forecast.holdout_d30_to_d90_error)": "Holdout error D90"})
p.footer(SRC_SIM)
pages.append(p)

# ======================= Page 5 - A/B test =======================
p = Page("d5f3a4b6c7e8d9f0a1b2", "5 · A/B test (Cookie Cats)")
p.header("Keep the first gate at level 30: moving it to 40 costs 0.8 pts of D7 retention",
         "Two-proportion z-test on 90,189 randomised players. The D7 gap is significant (p = 0.002) and the "
         "bootstrap finds gate 30 ahead in 100% of resamples. The D1 gap is not significant (p = 0.07).",
         "REAL DATA · COOKIE CATS")
g30, g40 = agg_sum("AB Test", "gate_30"), agg_sum("AB Test", "gate_40")
cw = W * 0.6
h = BOT - TOP - 180 - GAP
p.chart("abChart", "clusteredColumnChart", L, TOP, cw, h,
        {"Category": [C("AB Test", "metric")], "Y": [g30, g40]},
        "Retention rate by variant",
        {"dataPoint": [series_color(g30, BLUE), series_color(g40, "#B4B2A9")],
         "labels": [{"properties": {"show": lit(True), "color": color(INK)}}]},
        labels={qref(g30): "Gate 30 (control)", qref(g40): "Gate 40 (test)"})
cx = L + cw + GAP
ch = (h - GAP) / 2
p.card("gap", cx, TOP, R - cx, ch, "AB D7 Gap (pts)", "D7 retention gap, gate 30 minus gate 40 (pts)")
p.card("pvalue", cx, TOP + ch + GAP, R - cx, ch, "AB D7 p-value", "D7 p-value (two-sided z-test)")
y = TOP + h + GAP
ab_cols = ["metric", "gate_30", "gate_40", "difference_pts", "ci_low_pts", "ci_high_pts", "p_value", "prob_gate30_better"]
ab_labels = {"AB Test.metric": "Metric", "AB Test.gate_30": "Gate 30", "AB Test.gate_40": "Gate 40",
             "AB Test.difference_pts": "Gap (pts)", "AB Test.ci_low_pts": "95% CI low (pts)",
             "AB Test.ci_high_pts": "95% CI high (pts)", "AB Test.p_value": "p-value",
             "AB Test.prob_gate30_better": "P(gate 30 better), bootstrap"}
p.chart("abTable", "tableEx", L, y, W, BOT - y, {"Values": [C("AB Test", c) for c in ab_cols]},
        "Test statistics (a CI that excludes 0 means the gap is significant)", table_style(), labels=ab_labels)
p.footer(SRC_CC)
pages.append(p)

# ---------- write ----------
keep = {pg.pid for pg in pages}
for d in PAGES.iterdir():
    if d.is_dir() and d.name not in keep:
        shutil.rmtree(d)
for pg in pages:
    pg.write()
meta = {"$schema": PAGES_SCHEMA, "pageOrder": [pg.pid for pg in pages], "activePageName": pages[0].pid}
(PAGES / "pages.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print("pages:", [(pg.name.encode("ascii", "replace").decode(), len(pg.visuals)) for pg in pages])
