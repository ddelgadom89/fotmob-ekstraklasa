# =============================================================================
# Scraping automático FotMob - Ekstraklasa (estadísticas de jugadores)
# Se ejecuta solo con GitHub Actions y guarda el CSV en data/
#
# v2 (nov 2026): FotMob ya no incluye __NEXT_DATA__ en las páginas de stats,
# así que se usa la API JSON (mismo método que fotmob_attack.py). Ventajas:
#   - no depende del HTML de la web
#   - la temporada se detecta sola (no hay SEASON_ID fijo)
# El CSV de salida mantiene exactamente las mismas columnas que antes.
# =============================================================================

import os
import time
from datetime import date

import pandas as pd
from curl_cffi import requests  # imita un navegador real

LEAGUE_ID = 196        # Ekstraklasa
OUT_DIR = "data"

STATS = [
    "expected_goals",
    "goals",
    "expected_assists",
    "goal_assist",
    "big_chance_created",
    "goals_per_90",
    "expected_goals_per_90",
]

s = requests.Session(impersonate="chrome")


def buscar_urls(obj, out):
    """Recoge todas las URLs 'fetchAllUrl' de estadísticas del JSON de la liga."""
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
    raise SystemExit("No se pudo leer la API de la liga en FotMob.")


def posicion_de(p):
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


def posiciones_previas():
    path = f"{OUT_DIR}/ekstraklasa_players.csv"
    if not os.path.exists(path):
        return {}
    d = pd.read_csv(path, encoding="utf-8-sig")
    if "id" in d and "position" in d:
        return d.dropna(subset=["position"]).set_index("id")["position"].astype(int).to_dict()
    return {}


def main():
    urls = buscar_urls(datos_liga(), set())
    disponibles = {u.rsplit("/", 1)[-1].replace(".json", ""): u for u in urls if "/stats/" in u}
    sel = {k: u for k, u in disponibles.items() if k in STATS}
    print("Encontradas:", sorted(sel))
    print("No encontradas:", sorted(set(STATS) - set(sel)))
    if not sel:
        raise SystemExit("No se pudo descargar ninguna estadística")

    filas = []
    for stat, url in sel.items():
        try:
            j = s.get(url, timeout=30).json()
        except Exception as e:
            print(f"ERR {stat}: {e}")
            continue
        n = 0
        for lista in j.get("TopLists", []):
            for p in lista.get("StatList", []):
                filas.append({
                    "id": p.get("ParticiantId") or p.get("ParticipantId"),
                    "name": p.get("ParticipantName"),
                    "teamId": p.get("TeamId"),
                    "position": posicion_de(p),
                    "minutes": p.get("MinutesPlayed") or 0,
                    "stat": stat,
                    "value": p.get("StatValue"),
                    "sub": p.get("SubStatValue"),
                })
                n += 1
        print(f"OK  {stat}: {n} jugadores")
        time.sleep(1)

    if not filas:
        raise SystemExit("No se pudo descargar ninguna estadística")

    largo = pd.DataFrame(filas)
    base = (largo.sort_values("minutes", ascending=False)
                 .drop_duplicates("id")[["id", "name", "teamId"]])
    pos = largo.dropna(subset=["position"]).drop_duplicates("id").set_index("id")["position"]
    base["position"] = base["id"].map(pos).fillna(base["id"].map(posiciones_previas())).astype("Int64")

    valores = largo.pivot_table(index="id", columns="stat", values="value", aggfunc="first")
    players = base.merge(valores, on="id", how="left")
    # En las métricas por 90 se guarda también el valor secundario (igual que antes)
    for stat in [x for x in STATS if x.endswith("_per_90") and x in sel]:
        sub = largo[largo.stat == stat].drop_duplicates("id").set_index("id")["sub"]
        players[f"{stat}_sub"] = players["id"].map(sub)

    orden = ["id", "name", "teamId", "position"]
    for stat in STATS:
        if stat in players:
            orden.append(stat)
        if f"{stat}_sub" in players:
            orden.append(f"{stat}_sub")
    players = players[orden]
    players["updated"] = date.today().isoformat()

    os.makedirs(f"{OUT_DIR}/history", exist_ok=True)
    players.to_csv(f"{OUT_DIR}/ekstraklasa_players.csv", index=False, encoding="utf-8-sig")
    players.to_csv(f"{OUT_DIR}/history/ekstraklasa_players_{date.today()}.csv",
                   index=False, encoding="utf-8-sig")
    print(f"Guardado: {len(players)} jugadores")


if __name__ == "__main__":
    main()
