"""Generate or purge labelled simulated trips through the real GeoRutex pipeline.

Run inside the Odoo container with ``odoo shell`` (``env`` is provided):

    docker exec -i -e GRX_SIM_COUNT=300 -e GRX_SIM_DAYS=60 georutex-odoo \
        sh -c 'odoo shell -c /etc/odoo/odoo.conf --db_host=$HOST --db_user=$USER \
        --db_password=$PASSWORD -d georutex --no-http' < scripts/simulate_trips.py

Environment variables:
    GRX_SIM_COUNT  number of trips to generate (default 50)
    GRX_SIM_DAYS   spread trips over the last N days (default 30)
    GRX_SIM_SEED   random seed for reproducible batches (default 2026)
    GRX_SIM_BATCH  batch label (default SIM-<timestamp>)
    GRX_SIM_PURGE  "all" deletes every simulator batch, or a batch label to delete one

Requires approved routes with reference polyline and >= 4 stops, active vehicles
and users in the driver group. Every trip and position is stored as simulated.
"""

from datetime import datetime
import os

CHUNK = 20

service = env["transport.trip.simulation.service"]  # noqa: F821 (odoo shell global)
purge = os.environ.get("GRX_SIM_PURGE", "").strip()

if purge:
    removed = service.purge(None if purge == "all" else purge)
    env.cr.commit()  # noqa: F821
    print(f"Simulated trips removed: {removed}")
else:
    count = int(os.environ.get("GRX_SIM_COUNT", "50"))
    days = int(os.environ.get("GRX_SIM_DAYS", "30"))
    seed = int(os.environ.get("GRX_SIM_SEED", "2026"))
    batch = os.environ.get("GRX_SIM_BATCH") or datetime.now().strftime("SIM-%Y%m%d-%H%M%S")
    specs = service.plan_trips(count, days, seed, batch)
    print(f"Batch {batch}: {len(specs)} trips planned over the last {days} days.")
    done = 0
    for spec in specs:
        service.simulate_trip(spec)
        done += 1
        if done % CHUNK == 0:
            env.cr.commit()  # noqa: F821
            print(f"  {done}/{len(specs)} trips simulated")
    env.cr.commit()  # noqa: F821
    print(f"Done: {done} simulated trips in batch {batch}.")
