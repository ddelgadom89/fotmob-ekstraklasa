"""
Estadísticas de ATAQUE de la Ekstraklasa desde FotMob (todas las posiciones).
Guarda:
  data/fotmob_attack_latest.csv   -> foto actual
  data/fotmob_attack_history.csv  -> histórico (una foto por fecha)

Columnas: jugador, equipo, minutos, partidos, posición (código FotMob),
grupo (POR/DEF/MED/DEL) y cada estadística con su valor y _sub
(en FotMob el _sub suele ser el total o el % que acompaña al valor por 90).
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

# Categorías de ataque y creación (las que no existan en FotMob se saltan)
ATTACK_STATS = [
    # Finalización
    "goals", "goals_per_90", "expected_goals", "expected_goals_per_90",
    "expected_goalsontarget", "total_scoring_att", "ontarget_scoring_att",
    "big_chance_missed", "penalty_won", "touches_in_opp_box",
    # Creación
    "goal_assist", "expected_assists", "expected_assists_per_90",
    "_goals_and_goal_assist", "_expected_goals_and_expected_assists_per_90",
    "big_chance_created", "total_att_assist", "accurate_cross",
    # Conducción y pase
    "won_contest", "accurate_pass", "accurate_long_balls",
    # General
    "rating",
]

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
    url = f"https://www.fotmob.com/leagues/{LEAGUE_ID}/stats/ekstraklasa/players"
    r = s.get(url, timeout=30)
    print(f"{r.status_code} {url}")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        raise SystemExit("No se encontraron datos de la liga en FotMob.")
    return json.loads(m.group(1))


def posicion_de(p):
    """Código de posición FotMob si viene en el JSON (p. ej. 115 = delantero centro)."""
    for k in ("Positions", "Position", "PositionId", "position", "positionId"):
        v = p.get(k)
        if isinstance(v, list):
            v = v[0] if v else None
        if v not in (None, ""):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None
    return None


def grupo(code):
    """Código FotMob = fila*10 + columna en la pizarra -> línea del campo."""
    if pd.isna(code):
        return None
    code = int(code)
    if code < 10:
        return None          # códigos genéricos sin detalle
    fila = code // 10
    if fila == 1:
        return "POR"
    if fila in (2, 3, 4, 5):
        return "DEF"
    if fila in (6, 7, 8, 9):
        return "MED"
    return "DEL"


def posiciones_previas():
    """Plan B: posiciones guardadas por scrape_fotmob.py o por ejecuciones anteriores."""
    mapa = {}
    for path, id_col, pos_col in ((f"{OUT_DIR}/ekstraklasa_players.csv", "id", "position"),
                                  (f"{OUT_DIR}/fotmob_attack_latest.csv", "player_id", "position")):
        if os.path.exists(path):
            d = pd.read_csv(path, encoding="utf-8-sig")
            if id_col in d and pos_col in d:
                mapa.update(d.dropna(subset=[pos_col]).set_index(id_col)[pos_col].astype(int).to_dict())
    return mapa


def main():
    urls = buscar_urls(datos_liga(), set())
    stats = {u.rsplit("/", 1)[-1].replace(".json", ""): u for u in urls if "/stats/" in u}
    print("Categorías disponibles:", sorted(stats))

    sel = {k: u for k, u in stats.items() if k in ATTACK_STATS}
    print("Categorías de ataque:", sorted(sel))
    print("No encontradas:", sorted(set(ATTACK_STATS) - set(sel)))
    if not sel:
        raise SystemExit("No hay categorías de ataque: revisa la lista de arriba.")

    filas = []
    for stat, url in sel.items():
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
                    "position": posicion_de(p),
                    "stat": stat,
                    "value": p.get("StatValue"),
                    "sub_value": p.get("SubStatValue"),
                })
        time.sleep(1)

    largo = pd.DataFrame(filas)
    base = (largo.sort_values("minutes", ascending=False)
                 .drop_duplicates("player_id")
                 [["player_id", "player", "team_id", "team", "minutes", "matches"]])

    # Posición: la del JSON si viene; si no, la guardada antes
    pos = largo.dropna(subset=["position"]).drop_duplicates("player_id").set_index("player_id")["position"]
    previas = posiciones_previas()
    base["position"] = base["player_id"].map(pos).fillna(base["player_id"].map(previas))
    base["position"] = base["position"].astype("Int64")
    base["grupo"] = base["position"].map(grupo)

    valores = largo.pivot_table(index="player_id", columns="stat", values="value", aggfunc="first")
    subs = largo.pivot_table(index="player_id", columns="stat", values="sub_value", aggfunc="first")
    subs.columns = [f"{c}_sub" for c in subs.columns]
    df = base.merge(valores, on="player_id", how="left").merge(subs, on="player_id", how="left")
    df = df.dropna(axis=1, how="all")

    fecha = dt.date.today().isoformat()
    df.insert(0, "fecha", fecha)

    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(f"{OUT_DIR}/fotmob_attack_latest.csv", index=False)
    hist_path = f"{OUT_DIR}/fotmob_attack_history.csv"
    if os.path.exists(hist_path):
        hist = pd.read_csv(hist_path)
        df = pd.concat([hist[hist["fecha"] != fecha], df], ignore_index=True)
    df.to_csv(hist_path, index=False)
    n = df["fecha"].eq(fecha).sum()
    print(f"Guardado: {n} jugadores ({df.loc[df['fecha'].eq(fecha), 'grupo'].isna().sum()} sin posición)")


if __name__ == "__main__":
    main()
