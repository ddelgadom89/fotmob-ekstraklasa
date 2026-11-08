"""
Scraper de estadísticas de porteros de la Ekstraklasa (Sofascore).
Guarda:
  data/sofascore_gk_latest.csv   -> foto actual de la temporada
  data/sofascore_gk_history.csv  -> histórico (una foto por fecha de ejecución)
"""
import os
import time
import datetime as dt

import pandas as pd
from curl_cffi import requests  # imita un navegador Chrome (evita bloqueos 403)

BASE = "https://api.sofascore.com/api/v1"
TOURNAMENT_ID = 202  # Ekstraklasa
GROUPS = {               # grupo de estadísticas -> campo por el que ordenar
    "summary": "-rating",
    "goalkeeper": "-saves",
    "defence": "-clearances",
    "passing": "-accuratePasses",
}
OUT_DIR = "data"

s = requests.Session(impersonate="chrome")
s.headers.update({"Referer": "https://www.sofascore.com/", "Accept": "application/json"})


def get(url, params=None):
    for intento in range(4):
        r = s.get(url, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        print(f"  {r.status_code} en {url} (intento {intento + 1})")
        time.sleep(5 * (intento + 1))
    r.raise_for_status()


def temporada_actual():
    seasons = get(f"{BASE}/unique-tournament/{TOURNAMENT_ID}/seasons")["seasons"]
    return seasons[0]["id"], seasons[0]["year"]


def descargar_grupo(season_id, group, order):
    filas, offset = [], 0
    while True:
        data = get(
            f"{BASE}/unique-tournament/{TOURNAMENT_ID}/season/{season_id}/statistics",
            params={
                "limit": 100,
                "offset": offset,
                "order": order,
                "accumulation": "total",   # totales; los /90 se calculan en Colab
                "group": group,
                "filters": "position.in.G",  # solo porteros
            },
        )
        res = data.get("results", [])
        for r in res:
            p, t = r.pop("player", {}) or {}, r.pop("team", {}) or {}
            r.update(player_id=p.get("id"), player=p.get("name"),
                     team_id=t.get("id"), team=t.get("name"))
            filas.append(r)
        if not res or data.get("page", 1) >= data.get("pages", 1):
            break
        offset += 100
        time.sleep(1.5)
    return pd.DataFrame(filas)


def main():
    season_id, year = temporada_actual()
    print(f"Ekstraklasa {year} (season_id={season_id})")

    df = None
    for group, order in GROUPS.items():
        g = descargar_grupo(season_id, group, order)
        print(f"  {group}: {len(g)} porteros, {g.shape[1]} columnas")
        if g.empty:
            continue
        if df is None:
            df = g
        else:
            nuevas = [c for c in g.columns if c not in df.columns or c == "player_id"]
            df = df.merge(g[nuevas], on="player_id", how="outer")
        time.sleep(1.5)

    if df is None or df.empty:
        raise SystemExit("Sin datos: revisa si Sofascore está bloqueando la petición.")

    df = df.drop(columns=[c for c in ["id"] if c in df.columns])
    fecha = dt.date.today().isoformat()
    df.insert(0, "fecha", fecha)
    df.insert(1, "temporada", year)
    primeras = ["fecha", "temporada", "player_id", "player", "team_id", "team"]
    df = df[primeras + [c for c in df.columns if c not in primeras]]

    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(f"{OUT_DIR}/sofascore_gk_latest.csv", index=False)

    hist_path = f"{OUT_DIR}/sofascore_gk_history.csv"
    if os.path.exists(hist_path):
        hist = pd.read_csv(hist_path)
        hist = hist[hist["fecha"] != fecha]
        df = pd.concat([hist, df], ignore_index=True)
    df.to_csv(hist_path, index=False)
    print(f"Guardado: {len(df)} filas en histórico")


if __name__ == "__main__":
    main()
