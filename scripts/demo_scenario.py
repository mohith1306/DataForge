"""Deterministic demo scenario for DataForge.

Run with: uv run python scripts/demo_scenario.py

This script creates a schema drift incident and walks through
the full investigation → diagnosis → remediation → verification flow.
"""

import asyncio

import httpx

API_BASE = "http://localhost:8000/api"


async def main():
    print("=" * 60)
    print("DataForge Demo Scenario: Schema Drift Incident")
    print("=" * 60)

    async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
        # Step 1: Check health
        print("\n[1/7] Checking API health...")
        resp = await client.get("/health")
        print(f"  Status: {resp.json()}")

        # Step 2: Inject chaos fault
        print("\n[2/7] Injecting schema drift fault...")
        resp = await client.post("/chaos/schema_drift")
        chaos = resp.json()
        incident_id = chaos["incident_id"]
        print(f"  Fault: {chaos['fault_type']}")
        print(f"  Incident ID: {incident_id}")
        print(f"  Message: {chaos['message']}")

        # Step 3: Check incident was created with investigating status
        print("\n[3/7] Verifying incident status...")
        resp = await client.get(f"/incidents/{incident_id}")
        incident = resp.json()
        print(f"  Status: {incident['status']}")
        print(f"  Type: {incident['incident_type']}")
        print(f"  Severity: {incident['severity']}")

        # Step 4: Check events
        print("\n[4/7] Checking investigation events...")
        resp = await client.get(f"/incidents/{incident_id}/events")
        events = resp.json()
        print(f"  Events count: {len(events)}")
        for e in events:
            print(f"    - [{e['type']}] {e['message']}")

        # Step 5: List all incidents
        print("\n[5/7] Listing all incidents...")
        resp = await client.get("/incidents/")
        incidents = resp.json()
        print(f"  Total incidents: {len(incidents)}")

        # Step 6: Check stats
        print("\n[6/7] Checking dashboard stats...")
        resp = await client.get("/incidents/stats")
        stats = resp.json()
        print(f"  Total: {stats['total']}")
        print(f"  Open: {stats['open']}")
        print(f"  Resolved: {stats['resolved']}")
        print(f"  Critical: {stats['critical']}")

        # Step 7: List available faults
        print("\n[7/7] Available chaos faults:")
        resp = await client.get("/chaos/faults")
        faults = resp.json()["faults"]
        for f in faults:
            print(f"  - {f['type']}: {f['description'][:50]}... [{f['severity']}]")

    print("\n" + "=" * 60)
    print("Demo complete! Open http://localhost:5173 to see the UI.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
