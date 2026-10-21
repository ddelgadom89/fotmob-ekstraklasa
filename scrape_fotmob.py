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
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}

PATTERN = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'


def get_stat(stat):
    url = (f"https://www.fotmob.com/es/leagues/{LEAGUE_ID}/stats/season/"
           f"{SEASON_ID}/players/{stat}/ekstraklasa-players")
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()

    match = re.search(PATTERN, r.text, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError(f"No se encontró __NEXT_DATA__ para {stat}")

    page_props = json.loads(match.group(1))["props"]["pageProps"]
    df = pd.DataFrame(page_props["statsData"])

    df[stat] = df["statValue"].apply(lambda x: x.get("value") if isinstance(x, dict) else None)
    return df[["id", "name", "teamId", "position", stat]]


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
