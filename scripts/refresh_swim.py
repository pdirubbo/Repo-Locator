#!/usr/bin/env python3
"""Build the repo board from TFMS SWIM only. No ADS-B."""
import json, os, re, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "flights.json"
CALL = re.compile(r"^[A-Z]{3}[89]\d{3}$")
DONE = {"ARRIVED", "LANDED", "COMPLETED", "COMPLETE", "CANCELLED", "CANCELED"}
QUEUE = "pdirubbo0.gmail.com.TFMS.e51e74d4-cc2f-4bc2-9071-e423263d7e6a.OUT"
CARGO = {"GTI", "FDX", "UPS", "QTR", "CAO", "CCA", "AJT", "BVN", "MTN", "UAE"}
REG = {"SKW", "RPA", "ENY", "QXE", "EDV", "PDT", "JIA"}
AIRPORTS = {
    "ATL": (33.6407, -84.4277, "Atlanta"), "BOS": (42.3656, -71.0096, "Boston"),
    "CLT": (35.214, -80.9431, "Charlotte"), "DCA": (38.8521, -77.0377, "Washington"),
    "DEN": (39.8561, -104.6737, "Denver"), "DFW": (32.8998, -97.0403, "Dallas"),
    "DTW": (42.2124, -83.3534, "Detroit"), "EWR": (40.6925, -74.1687, "Newark"),
    "IAH": (29.9844, -95.3414, "Houston"), "JFK": (40.6398, -73.7789, "New York"),
    "LAS": (36.0801, -115.1522, "Las Vegas"), "LAX": (33.9425, -118.408, "Los Angeles"),
    "MCO": (28.4294, -81.3089, "Orlando"), "MIA": (25.7959, -80.287, "Miami"),
    "MSP": (44.882, -93.2218, "Minneapolis"), "ORD": (41.9742, -87.9073, "Chicago"),
    "PHL": (39.8719, -75.2411, "Philadelphia"), "PHX": (33.4343, -112.0116, "Phoenix"),
    "SAN": (32.7336, -117.1897, "San Diego"), "SEA": (47.4502, -122.3088, "Seattle"),
    "SFO": (37.6213, -122.379, "San Francisco"), "SLC": (40.7884, -111.9778, "Salt Lake City"),
    "SDF": (38.1744, -85.736, "Louisville"), "MEM": (35.0424, -89.9767, "Memphis"),
    "MDW": (41.786, -87.7524, "Chicago"), "ANC": (61.1744, -149.996, "Anchorage"),
}

def label(code):
    hit = AIRPORTS.get(code)
    return f"{code} {hit[2]}" if hit else code

def pack(cs, origin, dest, route, status):
    row = {
        "callsign": cs, "op": cs[:3], "type": "", "band": cs[3],
        "cargo": cs[:3] in CARGO, "regional": cs[:3] in REG,
        "origin": label(origin), "dest": label(dest),
        "route": route or f"{origin}-{dest}", "routeNote": "TFMS SWIM",
        "status": status or "filed", "alt": "filed", "gs": 0,
        "lat": None, "lon": None,
    }
    if origin in AIRPORTS:
        row.update(olat=AIRPORTS[origin][0], olon=AIRPORTS[origin][1])
    if dest in AIRPORTS:
        row.update(dlat=AIRPORTS[dest][0], dlon=AIRPORTS[dest][1])
    return row

def main():
    password = os.environ.get("SWIM_PASSWORD") or ""
    if not password:
        raise SystemExit("SWIM_PASSWORD is not set")
    from solace.messaging.messaging_service import MessagingService
    from solace.messaging.config.solace_properties import (
        transport_layer_properties as tp, transport_layer_security_properties as tls,
        service_properties as sp, authentication_properties as ap,
    )
    from solace.messaging.resources.queue import Queue
    props = {
        tp.HOST: "tcps://ems1.swim.faa.gov:55443", sp.VPN_NAME: "TFMS",
        ap.SCHEME_BASIC_USER_NAME: "pdirubbo0.gmail.com", ap.SCHEME_BASIC_PASSWORD: password,
        tls.CERT_VALIDATED: False, tls.CERT_VALIDATE_SERVERNAME: False,
    }
    svc = MessagingService.builder().from_properties(props).build()
    svc.connect()
    receiver = svc.create_persistent_message_receiver_builder().build(Queue.durable_exclusive_queue(QUEUE))
    receiver.start()
    pat = re.compile(r"<[^>]*aircraftId>([A-Z0-9]{3,8})<")
    dep = re.compile(r"<[^>]*departurePoint>.*?<[^>]*airport>([A-Z0-9]{3,4})<", re.S)
    arr = re.compile(r"<[^>]*arrivalPoint>.*?<[^>]*airport>([A-Z0-9]{3,4})<", re.S)
    status = re.compile(r"<[^>]*status>([^<]+)<")
    found, landed, n, end = {}, set(), 0, time.time() + 120
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
            cs = m.group(1)
            st = status.search(block).group(1).upper() if status.search(block) else ""
            if st in DONE:
                landed.add(cs)
                found.pop(cs, None)
                continue
            d, a = dep.search(block), arr.search(block)
            if d and a and cs not in landed:
                route = " ".join(x.strip() for x in re.findall(r"<[^>]*(?:route|Route)[^>]*>([^<]+)<", block) if x.strip())
                found[cs] = pack(cs, d.group(1), a.group(1), route, st or "filed")
    receiver.terminate()
    svc.disconnect()
    prev = json.loads(OUT.read_text()) if OUT.exists() else {"flights": []}
    old = {f["callsign"]: f for f in prev.get("flights", []) if CALL.match(f.get("callsign", ""))}
    if not found and n == 0:
        print("SWIM returned no messages, leaving flights.json unchanged")
        return
    merged = [row for cs, row in found.items() if cs not in landed]
    if len(merged) < 5:
        for cs, kept in old.items():
            if cs not in found and cs not in landed:
                merged.append(kept)
    merged.sort(key=lambda f: f["callsign"])
    OUT.write_text(json.dumps({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": "tfms-swim", "flights": merged}, indent=2) + "\n")
    print(f"SWIM messages {n}, repos {len(found)}, landed {len(landed)}, table {len(merged)}")

if __name__ == "__main__":
    main()
