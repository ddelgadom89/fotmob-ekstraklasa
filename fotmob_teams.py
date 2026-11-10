"""
Estadísticas de equipos de la Ekstraklasa desde FotMob.
Guarda:
  data/fotmob_teams_latest.csv   -> foto actual (una fila por equipo)
  data/fotmob_teams_history.csv  -> histórico (una foto por fecha)
"""
import os
import re
import json
import time
import datetime as dt

import pandas as pd
from curl_cffi import requests

LEAGUE_ID = 196  # Ekstraklasa
OUT_DIR = "data"

s = requests.Session(impersonate="chrome")


def buscar_urls(obj, out):
    """Recoge todas las URLs 'fetchAllUrl' de estadísticas que haya en el JSON."""
    if isinstance(obj, dict):
        if isinstance(obj.get("fetchAllUrl"), str):
            out.add(obj["fetchAllUrl"])
        for v in obj.values():
            buscar_urls(v, out)
    elif isinstance(obj, list):
        for v in obj:
            buscar_urls(v, out)
    return out


def datos_liga():
    for url in (f"https://www.fotmob.com/api/data/leagues?id={LEAGUE_ID}",
                f"https://www.fotmob.com/api/leagues?id={LEAGUE_ID}"):
        r = s.get(url, timeout=30)
        print(f"{r.status_code} {url}")
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                pass
    url = f"https://www.fotmob.com/leagues/{LEAGUE_ID}/stats/ekstraklasa/teams"
    r = s.get(url, timeout=30)
    print(f"{r.status_code} {url}")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        raise SystemExit("No se encontraron datos de la liga en FotMob.")
    return json.loads(m.group(1))


def nombre_columna(stat):
    """'expected_goals_team' -> 'expected_goals' ; 'goals_team_match' -> 'goals_match'"""
    return stat.replace("_team", "").strip("_")


def main():
    urls = buscar_urls(datos_liga(), set())
    stats = {u.rsplit("/", 1)[-1].replace(".json", ""): u for u in urls if "/stats/" in u}
    team_stats = {k: u for k, u in stats.items() if "_team" in k}
    print(f"Categorías de equipo ({len(team_stats)}):", sorted(team_stats))
    if not team_stats:
        raise SystemExit("No hay categorías de equipo.")

    filas = []
    for stat, url in team_stats.items():
        try:
            j = s.get(url, timeout=30).json()
        except Exception as e:
            print(f"  fallo en {stat}: {e}")
            continue
        for lista in j.get("TopLists", []):
            for p in lista.get("StatList", []):
                filas.append({
                    "team_id": p.get("TeamId") or p.get("ParticiantId") or p.get("ParticipantId"),
                    "team": p.get("ParticipantName") or p.get("TeamName"),
                    "matches": p.get("MatchesPlayed"),
                    "stat": nombre_columna(stat),
                    "value": p.get("StatValue"),
                    "sub_value": p.get("SubStatValue"),
                })
        time.sleep(1)

    largo = pd.DataFrame(filas)
    base = (largo.sort_values("matches", ascending=False)
                 .drop_duplicates("team_id")[["team_id", "team", "matches"]])
    valores = largo.pivot_table(index="team_id", columns="stat", values="value", aggfunc="first")
    subs = largo.pivot_table(index="team_id", columns="stat", values="sub_value", aggfunc="first")
    subs.columns = [f"{c}_sub" for c in subs.columns]
    df = base.merge(valores, on="team_id", how="left").merge(subs, on="team_id", how="left")
    df = df.dropna(axis=1, how="all").sort_values("team")

    fecha = dt.date.today().isoformat()
    df.insert(0, "fecha", fecha)

    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(f"{OUT_DIR}/fotmob_teams_latest.csv", index=False)
    hist_path = f"{OUT_DIR}/fotmob_teams_history.csv"
    if os.path.exists(hist_path):
        hist = pd.read_csv(hist_path)
        df = pd.concat([hist[hist["fecha"] != fecha], df], ignore_index=True)
    df.to_csv(hist_path, index=False)
    print(f"Guardado: {df['fecha'].eq(fecha).sum()} equipos, {df.shape[1]} columnas")


if __name__ == "__main__":
    main()
