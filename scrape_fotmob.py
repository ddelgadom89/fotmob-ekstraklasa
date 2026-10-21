# =============================================================================
# Scraping automático FotMob - Ekstraklasa (estadísticas de jugadores)
# Se ejecuta solo con GitHub Actions y guarda el CSV en data/
# =============================================================================

import os
import re
import json
import time
from datetime import date

import requests
import pandas as pd

LEAGUE_ID = 196        # Ekstraklasa
SEASON_ID = 37304      # Temporada actual

# Slugs de estadísticas: cópialos de la URL de FotMob al cambiar de pestaña
# (.../players/<slug>/ekstraklasa-players)
STATS = [
    "expected_goals",
    "goals",
    "expected_assists",
    "goal_assist",
    "big_chance_created",
    "goals_per_90",
    "expected_goals_per_90",
]

HEADERS = {
    # Mismo User-Agent que funcionó en Colab
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_3_2 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3.1 "
                  "Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

PATTERN = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'


def find_key(obj, key):
    """Busca una clave en cualquier nivel del JSON."""
    if isinstance(obj, dict):
        if key in obj and obj[key]:
            return obj[key]
        for v in obj.values():
            found = find_key(v, key)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = find_key(v, key)
            if found:
                return found
    return None


def get_stat(stat):
    url = (f"https://www.fotmob.com/es/leagues/{LEAGUE_ID}/stats/season/"
           f"{SEASON_ID}/players/{stat}/ekstraklasa-players")
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    match = re.search(PATTERN, r.text, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError(f"No se encontró __NEXT_DATA__ para {stat}")

    page_props = json.loads(match.group(1))["props"]["pageProps"]
    stats_data = find_key(page_props, "statsData")
    if not stats_data:
        print(f"   [debug] claves pageProps: {list(page_props.keys())}")
        print(f"   [debug] URL final: {r.url}")
        raise ValueError("statsData no encontrado")
    df = pd.DataFrame(stats_data)

    get_val = lambda x: x.get("value") if isinstance(x, dict) else None
    df[stat] = df["statValue"].apply(get_val)
    cols = ["id", "name", "teamId", "position", stat]

    # En las métricas por 90, el valor secundario suele ser el dato base (p. ej. minutos)
    if stat.endswith("_per_90") and "substatValue" in df.columns:
        df[f"{stat}_sub"] = df["substatValue"].apply(get_val)
        cols.append(f"{stat}_sub")

    return df[cols]


def main():
    frames = []
    for stat in STATS:
        try:
            df = get_stat(stat)
            frames.append(df.set_index(["id", "name", "teamId", "position"]))
            print(f"OK  {stat}: {len(df)} jugadores")
        except Exception as e:
            print(f"ERR {stat}: {e}")
        time.sleep(2)  # pausa para no saturar FotMob

    if not frames:
        raise SystemExit("No se pudo descargar ninguna estadística")

    players = pd.concat(frames, axis=1).reset_index()
    players["updated"] = date.today().isoformat()

    os.makedirs("data/history", exist_ok=True)
    players.to_csv("data/ekstraklasa_players.csv", index=False, encoding="utf-8-sig")
    players.to_csv(f"data/history/ekstraklasa_players_{date.today()}.csv",
                   index=False, encoding="utf-8-sig")
    print(f"Guardado: {len(players)} jugadores")


if __name__ == "__main__":
    main()
