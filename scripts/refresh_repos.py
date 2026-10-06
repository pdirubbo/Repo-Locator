#!/usr/bin/env python3
"""Refresh commercial 8xxx/9xxx repos and fill origin/destination."""
import json, re, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

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
    (51.47,-0.45),(50.04,8.56),(52.31,4.76),(25.25,55.36),
]
OPS = {
    "DAL":"Delta","SWA":"Southwest","FFT":"Frontier","JBU":"JetBlue","AAL":"American","UAL":"United","ASA":"Alaska","NKS":"Spirit",
    "SKW":"SkyWest","RPA":"Republic","EDV":"Endeavor","ENY":"Envoy","JIA":"PSA","PDT":"Piedmont","ASH":"Mesa","QXE":"Horizon",
    "UCA":"CommutAir","GJS":"GoJet","AWI":"Air Wisconsin","JZA":"Jazz","POE":"Porter","SIL":"Silver",
    "UAE":"Emirates SkyCargo","QTR":"Qatar Cargo","GTI":"Atlas Air","CJT":"Cargojet","FDX":"FedEx","UPS":"UPS",
    "KAL":"Korean Air Cargo","AJT":"Amerijet","CLX":"Cargolux","ABD":"Air Atlanta","BOX":"AeroLogic",
    "MTN":"Mountain Air Cargo","BVN":"Baron Aviation","IRO":"IFL Group",
}
CARGO = {"UAE","QTR","GTI","CJT","FDX","UPS","KAL","AJT","CLX","ABD","BOX","MTN","BVN","IRO"}
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

def label(airport):
    code = airport.get("iata") or airport.get("icao") or ""
    city = airport.get("location") or airport.get("name") or ""
    return f"{code} {city}".strip()

def route_for(cs):
    try:
        data = get(f"https://api.adsb.lol/api/0/route/{cs}")
    except Exception:
        return {}
    airports = data.get("_airports") or []
    if len(airports) < 2:
        return {}
    origin, nxt = airports[0], airports[1]
    dest = nxt if airports[-1].get("iata") == origin.get("iata") else airports[-1]
    out = {
        "origin": label(origin), "dest": label(dest),
        "olat": origin.get("lat"), "olon": origin.get("lon"),
        "dlat": dest.get("lat"), "dlon": dest.get("lon"),
        "routeNote": data.get("_airport_codes_iata") or data.get("airport_codes") or "adsb route",
    }
    if len(airports) > 2 and dest is not nxt:
        out.update(via=label(nxt), vlat=nxt.get("lat"), vlon=nxt.get("lon"))
    return out

def scan():
    found = {}
    for lat, lon in HUBS:
        for base in (f"https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/200", f"https://api.airplanes.live/v2/point/{lat}/{lon}/200"):
            try:
                data = get(base)
            except Exception:
                continue
            for ac in data.get("ac") or []:
                cs = (ac.get("flight") or "").strip().upper()
                if not commercial(cs, ac) or ac.get("lat") is None:
                    continue
                alt = ac.get("alt_baro")
                flying = str(alt).isdigit() and int(alt) > 100
                prefix = cs[:3]
                found[cs] = {
                    "callsign": cs, "reg": ac.get("r") or "", "type": ac.get("t") or "",
                    "lat": ac.get("lat"), "lon": ac.get("lon"),
                    "alt": int(alt) if flying else "ground", "gs": ac.get("gs") or 0,
                    "track": ac.get("track") or 0, "hex": ac.get("hex") or "",
                    "op": OPS.get(prefix, prefix), "band": cs[3],
                    "cargo": prefix in CARGO, "regional": prefix in REGIONAL,
                    "origin": "\u2014", "dest": "\u2014", "routeNote": "ADS-B refresh",
                }
            break
        time.sleep(0.15)
    return found

def main():
    prev = json.loads(OUT.read_text()) if OUT.exists() else {"flights": []}
    old = {f["callsign"]: f for f in prev.get("flights", []) if CALL.match(f.get("callsign",""))}
    live = scan()
    if not live:
        print("no commercial ADS-B results, leaving flights.json unchanged")
        return
    merged = []
    lookups = 0
    for cs, row in live.items():
        kept = old.get(cs, {})
        for key in ("origin","dest","via","olat","olon","dlat","dlon","vlat","vlon","routeNote"):
            if kept.get(key) not in (None, "", "\u2014"):
                row[key] = kept[key]
        if row.get("origin") in (None, "", "\u2014") and lookups < 40:
            found = route_for(cs)
            lookups += 1
            time.sleep(0.2)
            if found.get("origin"):
                row.update(found)
        merged.append(row)
    merged.sort(key=lambda f: f["callsign"])
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "adsb", "flights": merged}, indent=2) + "\n")
    print(f"wrote {len(merged)} flights, looked up {lookups} routes")

if __name__ == "__main__":
    main()
