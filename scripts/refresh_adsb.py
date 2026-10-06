#!/usr/bin/env python3
"""Update airborne positions only. A short scan must not wipe the board."""
import json, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "flights.json"
CALL = re.compile(r"^[A-Z]{3}[89]\d{3}$")
GA = {"C172","C152","C182","C206","C208","C210","PA28","PA32","BE35","BE36","BE58","SR22","M20P","CH7A","RV10","P28A"}
HUBS = [
    (33.64,-84.43),(33.94,-118.41),(41.97,-87.91),(32.90,-97.04),(39.86,-104.67),
    (40.64,-73.78),(28.43,-81.31),(36.08,-115.15),(35.21,-80.94),(25.80,-80.29),
    (47.45,-122.31),(40.69,-74.17),(37.62,-122.38),(33.44,-112.01),(29.98,-95.34),
    (42.36,-71.01),(44.88,-93.22),(40.77,-73.87),(42.21,-83.35),(39.87,-75.24),
    (40.79,-111.98),(38.85,-77.04),(38.94,-77.46),(36.13,-86.68),(29.99,-90.26),
]
OPS = {
    "DAL":"Delta","SWA":"Southwest","FFT":"Frontier","JBU":"JetBlue","AAL":"American","UAL":"United","ASA":"Alaska","NKS":"Spirit",
    "SKW":"SkyWest","RPA":"Republic","EDV":"Endeavor","ENY":"Envoy","JIA":"PSA","PDT":"Piedmont","ASH":"Mesa","QXE":"Horizon",
    "UCA":"CommutAir","GJS":"GoJet","AWI":"Air Wisconsin","JZA":"Jazz","POE":"Porter","SIL":"Silver",
    "UAE":"Emirates SkyCargo","QTR":"Qatar Cargo","GTI":"Atlas Air","CJT":"Cargojet","FDX":"FedEx","UPS":"UPS",
}
CARGO = {"UAE","QTR","GTI","CJT","FDX","UPS"}
REGIONAL = {"SKW","RPA","EDV","ENY","JIA","PDT","ASH","QXE","UCA","GJS","AWI","JZA","POE","SIL"}

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"repo-locator/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())

def commercial(cs, ac):
    if not CALL.match(cs) or cs.startswith("N"):
        return False
    prefix = cs[:3]
    typ = (ac.get("t") or "").upper()
    cat = (ac.get("category") or "").upper()
    if typ in GA and prefix not in CARGO:
        return False
    if cat in {"A1","A2"} and prefix not in CARGO:
        return False
    return prefix in OPS or prefix in CARGO or prefix in REGIONAL or cat in {"A3","A4","A5"}

def scan():
    airborne, landed, errors = {}, set(), 0
    for lat, lon in HUBS:
        try:
            data = get(f"https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/200")
        except Exception:
            errors += 1
            continue
        for ac in data.get("ac") or []:
            cs = (ac.get("flight") or "").strip().upper()
            if not commercial(cs, ac) or ac.get("lat") is None:
                continue
            alt = ac.get("alt_baro")
            if not (str(alt).isdigit() and int(alt) > 100):
                landed.add(cs)
                airborne.pop(cs, None)
                continue
            prefix = cs[:3]
            airborne[cs] = {
                "lat": ac.get("lat"), "lon": ac.get("lon"), "alt": int(alt),
                "gs": ac.get("gs") or 0, "track": ac.get("track") or 0,
                "reg": ac.get("r") or "", "type": ac.get("t") or "", "hex": ac.get("hex") or "",
                "op": OPS.get(prefix, prefix), "band": cs[3],
                "cargo": prefix in CARGO, "regional": prefix in REGIONAL,
            }
        time.sleep(0.12)
    return airborne, landed, errors

def main():
    prev = json.loads(OUT.read_text()) if OUT.exists() else {"flights": []}
    old = {f["callsign"]: f for f in prev.get("flights", []) if CALL.match(f.get("callsign",""))}
    live, landed, errors = scan()
    thin = errors > 5 or len(live) < max(3, len(old) // 2)
    merged = []
    for cs, pos in live.items():
        row = dict(old.get(cs, {}))
        row.update(pos)
        row["callsign"] = cs
        row.setdefault("origin", "\u2014")
        row.setdefault("dest", "\u2014")
        row.setdefault("route", "")
        row.setdefault("routeNote", "ADS-B")
        merged.append(row)
    for cs, kept in old.items():
        if cs in live or cs in landed:
            continue
        if thin or kept.get("alt") == "filed" or kept.get("lat") not in (None, ""):
            merged.append(kept)
    merged.sort(key=lambda f: f["callsign"])
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "adsb", "flights": merged}, indent=2) + "\n")
    print(f"positions {len(live)}, errors {errors}, thin {thin}, table {len(merged)}")

if __name__ == "__main__":
    main()
