#!/usr/bin/env python3
"""Fill missing origin, destination, and route after the position and TFMS jobs."""
import json, os, re, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "flights.json"
CALL = re.compile(r"^[A-Z]{3}[89]\d{3}$")
QUEUE = "pdirubbo0.gmail.com.TFMS.e51e74d4-cc2f-4bc2-9071-e423263d7e6a.OUT"
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
    "SDF": (38.1744,-85.736,"Louisville"), "MEM": (35.0424,-89.9767,"Memphis"),
    "CVG": (39.0488,-84.6678,"Cincinnati"), "SAN": (32.7336,-117.1897,"San Diego"),
}

def missing(row):
    return row.get("origin") in (None, "", "\u2014") or not row.get("route")

def pack(origin, dest, route, note):
    o = AIRPORTS.get(origin, (None, None, origin))
    d = AIRPORTS.get(dest, (None, None, dest))
    row = {"origin": f"{origin} {o[2]}", "dest": f"{dest} {d[2]}", "route": route or f"{origin}-{dest}", "routeNote": note}
    if o[0] is not None:
        row.update(olat=o[0], olon=o[1])
    if d[0] is not None:
        row.update(dlat=d[0], dlon=d[1])
    return row

def adsbdb(cs):
    url = f"https://api.adsbdb.com/v0/callsign/{cs}"
    req = urllib.request.Request(url, headers={"User-Agent":"repo-locator/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    fr = (data.get("response") or {}).get("flightroute") or {}
    o, d = fr.get("origin") or {}, fr.get("destination") or {}
    oc, dc = o.get("iata_code") or o.get("icao_code"), d.get("iata_code") or d.get("icao_code")
    if not oc or not dc:
        return {}
    return pack(oc, dc, f"{oc}-{dc}", "adsbdb route")

def tfms(needed):
    password = os.environ.get("SWIM_PASSWORD") or ""
    if not password or not needed:
        return {}
    from solace.messaging.messaging_service import MessagingService
    from solace.messaging.config.solace_properties import (
        transport_layer_properties as tp,
        transport_layer_security_properties as tls,
        service_properties as sp,
        authentication_properties as ap,
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
    found, end = {}, time.time() + 90
    while time.time() < end and needed - set(found):
        msg = receiver.receive_message(timeout=4000)
        if msg is None:
            continue
        body = msg.get_payload_as_string() or ""
        for block in re.split(r"<[^>]*flight[ >]", body)[1:]:
            m = pat.search(block)
            if not m or m.group(1) not in needed:
                continue
            d, a = dep.search(block), arr.search(block)
            if not (d and a):
                continue
            route = " ".join(x.strip() for x in re.findall(r"<[^>]*(?:route|Route)[^>]*>([^<]+)<", block) if x.strip())
            found[m.group(1)] = pack(d.group(1), a.group(1), route or f"{d.group(1)}-{a.group(1)}", "TFMS filed plan")
    receiver.terminate()
    svc.disconnect()
    return found

def main():
    data = json.loads(OUT.read_text()) if OUT.exists() else {"flights": []}
    rows = data.get("flights") or []
    gaps = [f for f in rows if CALL.match(f.get("callsign", "")) and missing(f)]
    print(f"{len(gaps)} flights missing a route")
    filled = 0
    for row in gaps:
        try:
            found = adsbdb(row["callsign"])
        except Exception:
            found = {}
        if found:
            row.update(found)
            filled += 1
        time.sleep(0.15)
    still = {f["callsign"] for f in rows if missing(f)}
    try:
        for cs, plan in tfms(still).items():
            for row in rows:
                if row.get("callsign") == cs:
                    row.update(plan)
                    filled += 1
    except Exception as exc:
        print("TFMS fill failed:", type(exc).__name__, exc)
    data["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data["source"] = "routes"
    data["flights"] = rows
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    print(f"filled {filled}, still missing {sum(missing(f) for f in rows)}")

if __name__ == "__main__":
    main()
