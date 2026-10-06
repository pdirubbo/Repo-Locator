#!/usr/bin/env python3
"""Refresh airborne 8xxx/9xxx repos from ADS-B and keep known routes."""
import json, re, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "flights.json"
CALL = re.compile(r"^[A-Z]{0,3}([89]\d{3})$")
HUBS = [
    (42.36, -71.01), (28.43, -81.31), (33.64, -84.43), (32.90, -97.04),
    (33.94, -118.41), (37.62, -122.38), (47.45, -122.31), (39.86, -104.67),
    (41.98, -87.90), (25.80, -80.29), (40.64, -73.78), (33.44, -112.01),
    (51.47, -0.45), (50.04, 8.56), (52.31, 4.76), (49.01, 2.55),
    (25.25, 55.36), (1.36, 103.99), (35.55, 139.78),
]
OPS = {
    "DAL":"Delta","SWA":"Southwest","FFT":"Frontier","JBU":"JetBlue","AAL":"American","UAL":"United","ASA":"Alaska","NKS":"Spirit",
    "RYR":"Ryanair","UAE":"Emirates SkyCargo","QTR":"Qatar Cargo","GTI":"Atlas Air","CJT":"Cargojet","FHY":"Freebird","HLF":"TUIfly","FDX":"FedEx","UPS":"UPS","CLX":"Cargolux",
    "SKW":"SkyWest","RPA":"Republic","EDV":"Endeavor","ENY":"Envoy","JIA":"PSA","PDT":"Piedmont","ASH":"Mesa","QXE":"Horizon",
    "UCA":"CommutAir","GJS":"GoJet","AWI":"Air Wisconsin","JZA":"Jazz","POE":"Porter","SIL":"Silver","KAP":"Cape Air","VTE":"Contour",
    "AMF":"Ameriflight","BTK":"Boutique","WSN":"Advanced Air","FDY":"Southern Airways","RVF":"Ravn",
    "CFE":"BA CityFlyer","KLC":"KLM Cityhopper","CLH":"Lufthansa CityLine","DLA":"Air Dolomiti","HOP":"Air France Hop","LOG":"Loganair","WIF":"Wideroe",
}
CARGO = {"UAE","QTR","GTI","CJT","FDX","UPS","CLX"}
REGIONAL = {"SKW","RPA","EDV","ENY","JIA","PDT","ASH","QXE","UCA","GJS","AWI","JZA","POE","SIL","KAP","VTE","AMF","BTK","WSN","FDY","RVF","CFE","KLC","CLH","DLA","HOP","LOG","WIF"}

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent":"repo-locator/1.0"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.loads(resp.read().decode())

def scan():
    found = {}
    for lat, lon in HUBS:
        for base in (f"https://api.adsb.lol/v2/point/{lat}/{lon}/250", f"https://api.airplanes.live/v2/point/{lat}/{lon}/250"):
            try:
                data = get(base)
            except Exception:
                continue
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
            if found:
                break
        time.sleep(0.4)
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
    print(f"wrote {len(merged)} flights")

if __name__ == "__main__":
    main()
