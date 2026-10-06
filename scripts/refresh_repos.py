#!/usr/bin/env python3
"""Refresh commercial 8xxx/9xxx repos. Drop a flight after it lands."""
import json, os, re, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "flights.json"
CALL = re.compile(r"^[A-Z]{3}[89]\d{3}$")
GA = {"C172","C152","C182","C206","C208","C210","PA28","PA32","BE35","BE36","BE58","SR22","M20P","CH7A","RV10","P28A"}
DONE = {"ARRIVED","LANDED","COMPLETED","COMPLETE","CANCELLED","CANCELED"}
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
AIRPORTS = {
    "PIT": (40.4915,-80.2329,"Pittsburgh"), "CLT": (35.214,-80.9431,"Charlotte"),
    "DTW": (42.2124,-83.3534,"Detroit"), "MCO": (28.4294,-81.3089,"Orlando"),
    "ATL": (33.6407,-84.4277,"Atlanta"), "ORD": (41.9742,-87.9073,"Chicago"),
    "DFW": (32.8998,-97.0403,"Dallas"), "DEN": (39.8561,-104.6737,"Denver"),
    "LAX": (33.9425,-118.408,"Los Angeles"), "SFO": (37.6213,-122.379,"San Francisco"),
    "SEA": (47.4502,-122.3088,"Seattle"), "JFK": (40.6398,-73.7789,"New York"),
    "EWR": (40.6925,-74.1687,"Newark"), "MIA": (25.7959,-80.287,"Miami"),
    "PHX": (33.4343,-112.0116,"Phoenix"), "LAS": (36.0801,-115.1522,"Las Vegas"),
    "BOS": (42.3656,-71.0096,"Boston"), "MSP": (44.882,-93.2218,"Minneapolis"),
    "SLC": (40.7884,-111.9778,"Salt Lake City"), "PHL": (39.8719,-75.2411,"Philadelphia"),
    "DCA": (38.8521,-77.0377,"Washington"), "IAD": (38.9445,-77.4558,"Dulles"),
    "IAH": (29.9844,-95.3414,"Houston"), "BWI": (39.1754,-76.6683,"Baltimore"),
    "SAN": (32.7336,-117.1897,"San Diego"), "TPA": (27.9755,-82.5332,"Tampa"),
    "SDF": (38.1744,-85.736,"Louisville"), "MEM": (35.0424,-89.9767,"Memphis"),
    "CVG": (39.0488,-84.6678,"Cincinnati"), "IND": (39.7173,-86.2944,"Indianapolis"),
}
QUEUE = "pdirubbo0.gmail.com.TFMS.e51e74d4-cc2f-4bc2-9071-e423263d7e6a.OUT"

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

def filed(origin, dest):
    o = AIRPORTS.get(origin, (None, None, origin))
    d = AIRPORTS.get(dest, (None, None, dest))
    row = {"origin": f"{origin} {o[2]}", "dest": f"{dest} {d[2]}", "routeNote": "TFMS filed plan"}
    if o[0] is not None:
        row.update(olat=o[0], olon=o[1])
    if d[0] is not None:
        row.update(dlat=d[0], dlon=d[1])
    return row

def swim_plans():
    password = os.environ.get("SWIM_PASSWORD") or ""
    if not password:
        print("SWIM_PASSWORD is not set")
        return {}, set()
    from solace.messaging.messaging_service import MessagingService
    from solace.messaging.config.solace_properties import (
        transport_layer_properties as tp,
        transport_layer_security_properties as tls,
        service_properties as sp,
        authentication_properties as ap,
    )
    from solace.messaging.resources.queue import Queue
    props = {
        tp.HOST: "tcps://ems1.swim.faa.gov:55443",
        sp.VPN_NAME: "TFMS",
        ap.SCHEME_BASIC_USER_NAME: "pdirubbo0.gmail.com",
        ap.SCHEME_BASIC_PASSWORD: password,
        tls.CERT_VALIDATED: False,
        tls.CERT_VALIDATE_SERVERNAME: False,
    }
    svc = MessagingService.builder().from_properties(props).build()
    svc.connect()
    receiver = svc.create_persistent_message_receiver_builder().build(Queue.durable_exclusive_queue(QUEUE))
    receiver.start()
    pat = re.compile(r"<[^>]*aircraftId>([A-Z0-9]{3,8})<")
    dep = re.compile(r"<[^>]*departurePoint>.*?<[^>]*airport>([A-Z0-9]{3,4})<", re.S)
    arr = re.compile(r"<[^>]*arrivalPoint>.*?<[^>]*airport>([A-Z0-9]{3,4})<", re.S)
    status = re.compile(r"<[^>]*status>([^<]+)<")
    found, landed, n, end = {}, set(), 0, time.time() + 40
    while time.time() < end:
        msg = receiver.receive_message(timeout=4000)
        if msg is None:
            continue
        body = msg.get_payload_as_string() or ""
        n += 1
        for block in re.split(r"<[^>]*flight[ >]", body)[1:]:
            m = pat.search(block)
            if not m or not CALL.match(m.group(1)):
                continue
            st = (status.search(block).group(1).upper() if status.search(block) else "")
            if st in DONE or "ARRIVAL" in body[max(0, body.find(m.group(1))-80):body.find(m.group(1))+40].upper():
                landed.add(m.group(1))
                found.pop(m.group(1), None)
                continue
            d, a = dep.search(block), arr.search(block)
            if d and a and m.group(1) not in landed:
                found[m.group(1)] = filed(d.group(1), a.group(1))
    receiver.terminate()
    svc.disconnect()
    print(f"TFMS messages {n}, filed repos {len(found)}, landed {len(landed)}")
    return found, landed

def scan():
    airborne, landed = {}, set()
    for lat, lon in HUBS:
        try:
            data = get(f"https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/200")
        except Exception:
            continue
        for ac in data.get("ac") or []:
            cs = (ac.get("flight") or "").strip().upper()
            if not commercial(cs, ac) or ac.get("lat") is None:
                continue
            alt = ac.get("alt_baro")
            flying = str(alt).isdigit() and int(alt) > 100
            if not flying:
                landed.add(cs)
                airborne.pop(cs, None)
                continue
            if cs in landed:
                continue
            prefix = cs[:3]
            airborne[cs] = {
                "callsign": cs, "reg": ac.get("r") or "", "type": ac.get("t") or "",
                "lat": ac.get("lat"), "lon": ac.get("lon"), "alt": int(alt),
                "gs": ac.get("gs") or 0, "track": ac.get("track") or 0, "hex": ac.get("hex") or "",
                "op": OPS.get(prefix, prefix), "band": cs[3],
                "cargo": prefix in CARGO, "regional": prefix in REGIONAL,
                "origin": "\u2014", "dest": "\u2014", "routeNote": "ADS-B refresh",
            }
        time.sleep(0.15)
    return airborne, landed

def filed_row(cs, plan):
    prefix = cs[:3]
    row = {
        "callsign": cs, "reg": "", "type": "", "lat": None, "lon": None,
        "alt": "filed", "gs": 0, "track": 0, "hex": "",
        "op": OPS.get(prefix, prefix), "band": cs[3],
        "cargo": prefix in CARGO, "regional": prefix in REGIONAL,
    }
    row.update(plan)
    return row

def main():
    plans, landed = {}, set()
    try:
        plans, landed = swim_plans()
    except Exception as exc:
        print("TFMS read failed:", type(exc).__name__, exc)
    prev = json.loads(OUT.read_text()) if OUT.exists() else {"flights": []}
    old = {f["callsign"]: f for f in prev.get("flights", []) if CALL.match(f.get("callsign",""))}
    live, on_ground = scan()
    landed |= on_ground
    merged, seen = [], set()
    for cs, row in live.items():
        if cs in landed:
            continue
        kept = old.get(cs, {})
        for key in ("origin","dest","olat","olon","dlat","dlon","routeNote"):
            if kept.get(key) not in (None, "", "\u2014"):
                row[key] = kept[key]
        if cs in plans:
            row.update(plans[cs])
        merged.append(row)
        seen.add(cs)
    for cs, plan in plans.items():
        if cs in seen or cs in landed:
            continue
        merged.append(filed_row(cs, plan))
        seen.add(cs)
    for cs, kept in old.items():
        if cs in seen or cs in landed:
            continue
        if kept.get("alt") == "ground":
            continue
        if kept.get("routeNote") == "TFMS filed plan" and kept.get("lat") in (None, ""):
            merged.append(kept)
    merged.sort(key=lambda f: f["callsign"])
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "adsb+tfms", "flights": merged}, indent=2) + "\n")
    print(f"wrote {len(merged)} flights, dropped {len(landed)} landed")

if __name__ == "__main__":
    main()
