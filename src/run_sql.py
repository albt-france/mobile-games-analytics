"""Load the CSVs into DuckDB and run every query in sql/, saving results to data/output/."""
import duckdb, pathlib
con = duckdb.connect()
for name, f in {"players": "sim_players", "daily_activity": "sim_daily_activity", "ua_spend": "sim_ua_spend"}.items():
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_csv_auto('data/clean/{f}.csv')")
out = pathlib.Path("data/output"); out.mkdir(exist_ok=True)
for q in sorted(pathlib.Path("sql").glob("*.sql")):
    df = con.execute(q.read_text()).df()
    df.to_csv(out / (q.stem + ".csv"), index=False)
    print(f"== {q.name}: {len(df)} rows"); print(df.head(12).to_string(index=False))
