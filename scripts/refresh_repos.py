#!/usr/bin/env python3
"""Refresh airborne 8xxx/9xxx repos from ADS-B and keep known routes."""
import json, re, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "flights.json"
CALL = re.compile(r"^[A-Z]{0,3}([89]\d{3})$")
# Major US airports, 200 nm each. A few overseas hubs stay so European repos are not dropped.
HUBS = [
    (33.64,-84.43),(33.94,-118.41),(41.97,-87.91),(32.90,-97.04),(39.86,-104.67),
    (40.64,-73.78),(28.43,-81.31),(36.08,-115.15),(35.21,-80.94),(25.80,-80.29),
    (47.45,-122.31),(40.69,-74.17),(37.62,-122.38),(33.44,-112.01),(29.98,-95.34),
    (42.36,-71.01),(26.07,-80.15),(44.88,-93.22),(40.77,-73.87),(42.21,-83.35),
    (39.87,-75.24),(40.79,-111.98),(39.18,-76.67),(38.85,-77.04),(32.73,-117.19),
    (38.94,-77.46),(27.98,-82.53),(41.79,-87.75),(36.13,-86.68),(30.19,-97.67),
    (21.32,-157.92),(32.85,-96.85),(45.59,-122.60),(38.75,-90.37),(29.65,-95.28),
    (35.88,-78.79),(29.99,-90.26),(38.70,-121.59),(37.36,-121.93),(33.68,-117.87),
    (39.30,-94.71),(29.53,-98.47),(39.72,-86.29),(39.05,-84.67),(41.41,-81.85),
    (40.49,-80.23),(40.00,-82.89),(42.95,-87.90),(37.72,-122.22),(41.94,-72.68),
    (30.49,-81.69),(26.54,-81.76),(26.68,-80.10),(42.94,-78.73),(41.30,-95.89),
    (35.04,-106.61),(32.12,-110.94),(35.04,-89.98),(61.17,-150.00),(38.17,-85.74),
    (36.89,-76.20),(37.51,-77.32),(32.90,-80.04),(33.56,-86.75),(35.39,-97.60),
    (36.20,-95.89),(31.81,-106.38),(38.81,-104.70),(43.56,-116.22),(47.62,-117.53),
    (34.06,-117.60),(18.44,-66.00),(26.07,-80.15),
    (51.47,-0.45),(50.04,8.56),(52.31,4.76),(25.25,55.36),
]
OPS = {
    "DAL":"Delta","SWA":"Southwest","FFT":"Frontier","JBU":"JetBlue","AAL":"American","UAL":"United","ASA":"Alaska","NKS":"Spirit",
    "RYR":"Ryanair","UAE":"Emirates SkyCargo","QTR":"Qatar Cargo","GTI":"Atlas Air","CJT":"Cargojet","FDX":"FedEx","UPS":"UPS",
    "SKW":"SkyWest","RPA":"Republic","EDV":"Endeavor","ENY":"Envoy","JIA":"PSA","PDT":"Piedmont","ASH":"Mesa","QXE":"Horizon",
    "UCA":"CommutAir","GJS":"GoJet","AWI":"Air Wisconsin","JZA":"Jazz","POE":"Porter","SIL":"Silver","KAP":"Cape Air",
}
CARGO = {"UAE","QTR","GTI","CJT","FDX","UPS"}
REGIONAL = {"SKW","RPA","EDV","ENY","JIA","PDT","ASH","QXE","UCA","GJS","AWI","JZA","POE","SIL","KAP"}

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"repo-locator/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())

def scan():
    found = {}
    for lat, lon in HUBS:
        got = False
        for base in (f"https://api.adsb.lol/v2/point/{lat}/{lon}/200", f"https://api.airplanes.live/v2/point/{lat}/{lon}/200"):
            try:
                data = get(base)
            except Exception:
                continue
            got = True
            for ac in data.get("ac") or []:
                cs = (ac.get("flight") or "").strip().upper()
                m = CALL.match(cs)
                if not m or ac.get("lat") is None or ac.get("lon") is None:
                    continue
                alt = ac.get("alt_baro")
                flying = str(alt).isdigit() and int(alt) > 100
                prefix = cs[:3] if len(cs) > 4 else ""
                found[cs] = {
                    "callsign": cs, "reg": ac.get("r") or "", "type": ac.get("t") or "",
                    "lat": ac.get("lat"), "lon": ac.get("lon"),
                    "alt": int(alt) if flying else "ground", "gs": ac.get("gs") or 0,
                    "track": ac.get("track") or 0, "hex": ac.get("hex") or "",
                    "op": OPS.get(prefix, prefix or "Unknown"), "band": m.group(1)[0],
                    "cargo": prefix in CARGO, "regional": prefix in REGIONAL,
                    "origin": "\u2014", "dest": "\u2014", "routeNote": "ADS-B refresh, route not looked up",
                }
            break
        if not got:
            time.sleep(0.4)
        time.sleep(0.15)
    return found

def main():
    prev = json.loads(OUT.read_text()) if OUT.exists() else {"flights": []}
    old = {f["callsign"]: f for f in prev.get("flights", [])}
    live = scan()
    if not live:
        print("no ADS-B results, leaving flights.json unchanged")
        return
    merged = []
    for cs, row in live.items():
        kept = old.get(cs, {})
        for key in ("origin","dest","via","olat","olon","dlat","dlon","vlat","vlon","routeNote"):
            if kept.get(key) not in (None, "", "\u2014"):
                row[key] = kept[key]
        merged.append(row)
    for cs, row in old.items():
        if cs not in live and row.get("olat") is not None:
            row = dict(row)
            row["alt"] = "ground"
            row["gs"] = 0
            merged.append(row)
    merged.sort(key=lambda f: f["callsign"])
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "adsb", "flights": merged}, indent=2) + "\n")
    print(f"wrote {len(merged)} flights from {len(HUBS)} hubs")

if __name__ == "__main__":
    main()
