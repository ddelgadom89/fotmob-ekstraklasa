"""
Estadísticas de porteros de la Ekstraklasa desde FotMob.
Guarda:
  data/fotmob_gk_latest.csv   -> foto actual
  data/fotmob_gk_history.csv  -> histórico (una foto por fecha)
"""
import os
import re
import json
import time
import datetime as dt

import pandas as pd
from curl_cffi import requests

LEAGUE_ID = 196  # Ekstraklasa
GK_STATS = [  # categorías de portero en FotMob
    "_goals_prevented", "_save_percentage", "saves", "clean_sheet", "goals_conceded",
    "penalty_save", "total_keeper_sweeper", "total_high_claim",
]
SOLO_PORTEROS = ["saves", "_save_percentage", "_goals_prevented"]  # quien aparece aquí es portero
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
    # Plan B: leer el JSON incrustado en la propia página web
    url = f"https://www.fotmob.com/leagues/{LEAGUE_ID}/stats/ekstraklasa/players"
    r = s.get(url, timeout=30)
    print(f"{r.status_code} {url}")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        raise SystemExit("No se encontraron datos de la liga en FotMob.")
    return json.loads(m.group(1))


def main():
    urls = buscar_urls(datos_liga(), set())
    stats = {u.rsplit("/", 1)[-1].replace(".json", ""): u for u in urls if "/stats/" in u}
    print("Categorías disponibles:", sorted(stats))

    gk_stats = {k: u for k, u in stats.items() if k in GK_STATS}
    print("Categorías de portero:", sorted(gk_stats))
    if not gk_stats:
        raise SystemExit("No hay categorías de portero: revisa la lista de arriba.")

    filas = []
    for stat, url in gk_stats.items():
        j = s.get(url, timeout=30).json()
        for lista in j.get("TopLists", []):
            for p in lista.get("StatList", []):
                filas.append({
                    "player_id": p.get("ParticiantId") or p.get("ParticipantId"),
                    "player": p.get("ParticipantName"),
                    "team_id": p.get("TeamId"),
                    "team": p.get("TeamName"),
                    "minutes": p.get("MinutesPlayed"),
                    "matches": p.get("MatchesPlayed"),
                    "stat": stat,
                    "value": p.get("StatValue"),
                    "sub_value": p.get("SubStatValue"),
                })
        time.sleep(1)

    largo = pd.DataFrame(filas)
    porteros = set(largo.loc[largo["stat"].isin(SOLO_PORTEROS), "player_id"])
    largo = largo[largo["player_id"].isin(porteros)]
    base = (largo.sort_values("minutes", ascending=False)
                 .drop_duplicates("player_id")[["player_id", "player", "team_id", "team",
                                                "minutes", "matches"]])
    valores = largo.pivot_table(index="player_id", columns="stat", values="value", aggfunc="first")
    subs = largo.pivot_table(index="player_id", columns="stat", values="sub_value", aggfunc="first")
    subs.columns = [f"{c}_sub" for c in subs.columns]
    df = base.merge(valores, on="player_id", how="left").merge(subs, on="player_id", how="left")
    df = df.dropna(axis=1, how="all")

    fecha = dt.date.today().isoformat()
    df.insert(0, "fecha", fecha)

    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(f"{OUT_DIR}/fotmob_gk_latest.csv", index=False)
    hist_path = f"{OUT_DIR}/fotmob_gk_history.csv"
    if os.path.exists(hist_path):
        hist = pd.read_csv(hist_path)
        df = pd.concat([hist[hist["fecha"] != fecha], df], ignore_index=True)
    df.to_csv(hist_path, index=False)
    print(f"Guardado: {df['fecha'].eq(fecha).sum()} porteros")


if __name__ == "__main__":
    main()
