#!/usr/bin/env python3
"""Detect 8xxx/9xxx flights from the FAA AADC feed for major US airports."""
import json, time, urllib.request, re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "flights.json"
CALL = re.compile(r"^[A-Z]{3}[89]\d{3}$")
AIRPORTS = "ATL BOS BWI CLT DCA DEN DFW DTW EWR FLL HNL IAD IAH JFK LAS LAX LGA MCO MDW MIA MSP ORD PDX PHL PHX PIT SAN SEA SFO SLC STL TPA AUS BNA CVG IND MCI MKE OAK RDU SJC SMF DAL HOU SAT SDF MEM ANC".split()
COORDS = {
    "ATL": (33.6407,-84.4277,"Atlanta"), "BOS": (42.3656,-71.0096,"Boston"), "BWI": (39.1754,-76.6683,"Baltimore"),
    "CLT": (35.214,-80.9431,"Charlotte"), "DCA": (38.8521,-77.0377,"Washington"), "DEN": (39.8561,-104.6737,"Denver"),
    "DFW": (32.8998,-97.0403,"Dallas"), "DTW": (42.2124,-83.3534,"Detroit"), "EWR": (40.6925,-74.1687,"Newark"),
    "FLL": (26.0726,-80.1527,"Fort Lauderdale"), "HNL": (21.3187,-157.9225,"Honolulu"), "IAD": (38.9445,-77.4558,"Dulles"),
    "IAH": (29.9844,-95.3414,"Houston"), "JFK": (40.6398,-73.7789,"New York"), "LAS": (36.0801,-115.1522,"Las Vegas"),
    "LAX": (33.9425,-118.408,"Los Angeles"), "LGA": (40.7772,-73.8726,"New York"), "MCO": (28.4294,-81.3089,"Orlando"),
    "MDW": (41.786,-87.7524,"Chicago"), "MIA": (25.7959,-80.287,"Miami"), "MSP": (44.882,-93.2218,"Minneapolis"),
    "ORD": (41.9742,-87.9073,"Chicago"), "PDX": (45.5898,-122.5951,"Portland"), "PHL": (39.8719,-75.2411,"Philadelphia"),
    "PHX": (33.4343,-112.0116,"Phoenix"), "PIT": (40.4915,-80.2329,"Pittsburgh"), "SAN": (32.7336,-117.1897,"San Diego"),
    "SEA": (47.4502,-122.3088,"Seattle"), "SFO": (37.6213,-122.379,"San Francisco"), "SLC": (40.7884,-111.9778,"Salt Lake City"),
    "STL": (38.7487,-90.37,"St Louis"), "TPA": (27.9755,-82.5332,"Tampa"), "AUS": (30.1945,-97.6699,"Austin"),
    "BNA": (36.1263,-86.6774,"Nashville"), "CVG": (39.0488,-84.6678,"Cincinnati"), "IND": (39.7173,-86.2944,"Indianapolis"),
    "MCI": (39.2976,-94.7139,"Kansas City"), "MKE": (42.9472,-87.8966,"Milwaukee"), "OAK": (37.7213,-122.221,"Oakland"),
    "RDU": (35.8776,-78.7875,"Raleigh"), "SJC": (37.3626,-121.929,"San Jose"), "SMF": (38.6954,-121.591,"Sacramento"),
    "DAL": (32.8471,-96.8518,"Dallas"), "HOU": (29.6454,-95.2789,"Houston"), "SAT": (29.5337,-98.4698,"San Antonio"),
    "SDF": (38.1744,-85.736,"Louisville"), "MEM": (35.0424,-89.9767,"Memphis"), "ANC": (61.1744,-149.996,"Anchorage"),
    "TUL": (36.1984,-95.8881,"Tulsa"), "OGG": (20.8986,-156.4305,"Kahului"),
}
CARGO = {"GTI","FDX","UPS","QTR","CAO","CCA","AJT","BVN","MTN"}
REG = {"SKW","RPA","ENY","QXE","EDV","PDT","JIA"}

def label(code):
    hit = COORDS.get(code)
    return f"{code} {hit[2]}" if hit else code

def main():
    found = {}
    for apt in AIRPORTS:
        url = f"https://www.fly.faa.gov/aadc/api/airports/{apt}"
        req = urllib.request.Request(url, headers={"User-Agent":"repo-locator/1.0"})
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
        except Exception as exc:
            print(apt, type(exc).__name__)
            continue
        for bucket in data.get("timeBuckets") or []:
            for fl in bucket.get("flights") or []:
                cs = (fl.get("acid") or "").strip().upper()
                if not CALL.match(cs):
                    continue
                origin, dest = fl.get("origin") or "", fl.get("destination") or ""
                row = found.setdefault(cs, {
                    "callsign": cs, "type": fl.get("type") or "", "op": fl.get("majorAirline") or cs[:3],
                    "band": cs[3], "cargo": cs[:3] in CARGO, "regional": cs[:3] in REG,
                    "routeNote": "FAA AADC", "alt": "filed", "gs": 0, "lat": None, "lon": None,
                })
                if origin: row["originCode"] = origin
                if dest: row["destCode"] = dest
                if fl.get("type"): row["type"] = fl["type"]
        time.sleep(0.05)
    flights = []
    for cs, row in sorted(found.items()):
        o, d = row.pop("originCode", ""), row.pop("destCode", "")
        row["origin"], row["dest"], row["route"] = label(o), label(d), f"{o}-{d}"
        if o in COORDS: row.update(olat=COORDS[o][0], olon=COORDS[o][1])
        if d in COORDS: row.update(dlat=COORDS[d][0], dlon=COORDS[d][1])
        flights.append(row)
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "faa-aadc", "flights": flights}, indent=2) + "\n")
    print(f"wrote {len(flights)} FAA repo flights")

if __name__ == "__main__":
    main()
