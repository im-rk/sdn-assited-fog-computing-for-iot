#!/usr/bin/env python3
"""
API Gateway - Unified Access Point
====================================
Aggregates data from:
  - Fog Server     (http://localhost:5101)
  - Cloud Server   (http://localhost:5102)
  - SDN Proxy      (http://localhost:9001) - routing decisions log

Exposes clean REST endpoints for the Dashboard.

Runs on: http://0.0.0.0:8000
"""

import asyncio
import aiohttp
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# -- Service URLs -------------------------------------------------------------
# Override with env vars for Mininet mode:
#   FOG_URL=http://10.0.0.4:5101 CLOUD_URL=http://10.0.0.5:5102 python3 gateway/api_gateway.py
FOG_URL   = os.environ.get("FOG_URL",   "http://localhost:5101")
CLOUD_URL = os.environ.get("CLOUD_URL", "http://localhost:5102")
PROXY_URL = os.environ.get("PROXY_URL", "http://localhost:9001")
RYU_STATS_URL = os.environ.get("RYU_STATS_URL", "http://127.0.0.1:9002")

GATEWAY_HOST = "0.0.0.0"
GATEWAY_PORT = 8000

app = FastAPI(
    title="SDN-IoT API Gateway",
    description="Unified REST API for SDN-Assisted Fog Computing for IoT",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- Helpers -------------------------------------------------------------------
async def fetch(session, url: str, timeout: int = 5):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            if r.status == 200:
                return await r.json()
            return {"error": f"HTTP {r.status}"}
    except Exception as e:
        return {"error": str(e)}


# -- Endpoints -----------------------------------------------------------------
@app.get("/")
async def root():
    return {
        "service": "SDN-IoT API Gateway v2",
        "endpoints": [
            "/health", "/status",
            "/fog/stats", "/fog/alerts",
            "/cloud/stats", "/cloud/data",
            "/sdn/stats", "/sdn/routing-log",
            "/dashboard"
        ]
    }


@app.get("/health")
async def health():
    async with aiohttp.ClientSession() as s:
        fog, cloud, proxy = await asyncio.gather(
            fetch(s, f"{FOG_URL}/health"),
            fetch(s, f"{CLOUD_URL}/health"),
            fetch(s, f"{PROXY_URL}/health"),
        )
    return {
        "gateway":    "healthy",
        "fog_server": fog,
        "cloud_server": cloud,
        "sdn_proxy": proxy,
        "timestamp":  datetime.now().isoformat()
    }


@app.get("/status")
async def status():
    async with aiohttp.ClientSession() as s:
        fog, cloud, proxy = await asyncio.gather(
            fetch(s, f"{FOG_URL}/stats"),
            fetch(s, f"{CLOUD_URL}/stats"),
            fetch(s, f"{PROXY_URL}/stats"),
        )
    return {"fog": fog, "cloud": cloud, "sdn_proxy": proxy,
            "timestamp": datetime.now().isoformat()}


@app.get("/fog/stats")
async def fog_stats():
    async with aiohttp.ClientSession() as s:
        r = await fetch(s, f"{FOG_URL}/stats")
    return r


@app.get("/fog/alerts")
async def fog_alerts():
    async with aiohttp.ClientSession() as s:
        r = await fetch(s, f"{FOG_URL}/alerts")
    return r


@app.get("/cloud/stats")
async def cloud_stats():
    async with aiohttp.ClientSession() as s:
        r = await fetch(s, f"{CLOUD_URL}/stats")
    return r


@app.get("/cloud/data")
async def cloud_data():
    async with aiohttp.ClientSession() as s:
        r = await fetch(s, f"{CLOUD_URL}/data")
    return r


@app.get("/sdn/stats")
async def sdn_stats():
    """SDN Proxy statistics - routing counts, classification breakdown."""
    async with aiohttp.ClientSession() as s:
        r = await fetch(s, f"{PROXY_URL}/stats")
    return r


@app.get("/sdn/routing-log")
async def sdn_routing_log():
    """Full routing decision log from the SDN Proxy."""
    async with aiohttp.ClientSession() as s:
        r = await fetch(s, f"{PROXY_URL}/routing-log")
    return r


@app.get("/metrics/comparison")
async def metrics_comparison():
    """
    Latency evaluation: Fog vs Cloud side-by-side.

    This is the core justification for SDN-Assisted Fog Computing:
    Emergency packets routed to Fog are processed in <5ms.
    The same packet sent to Cloud would take 50-150ms extra.
    The SDN controller makes this routing decision automatically via DPI.
    """
    async with aiohttp.ClientSession() as s:
        fog_m, cloud_m = await asyncio.gather(
            fetch(s, f"{FOG_URL}/metrics"),
            fetch(s, f"{CLOUD_URL}/metrics"),
        )

    fog_avg   = (fog_m.get('latency',   {}).get('total_ms',    {}) or {}).get('avg_ms', 0)
    cloud_avg = (cloud_m.get('latency', {}).get('total_ms',    {}) or {}).get('avg_ms', 0)
    fog_p95   = (fog_m.get('latency',   {}).get('total_ms',    {}) or {}).get('p95_ms', 0)
    cloud_p95 = (cloud_m.get('latency', {}).get('total_ms',    {}) or {}).get('p95_ms', 0)
    fog_p99   = (fog_m.get('latency',   {}).get('total_ms',    {}) or {}).get('p99_ms', 0)
    cloud_p99 = (cloud_m.get('latency', {}).get('total_ms',    {}) or {}).get('p99_ms', 0)

    speedup = round(cloud_avg / fog_avg, 1) if fog_avg > 0 else None

    return {
        'fog':   fog_m,
        'cloud': cloud_m,
        'comparison': {
            'fog_avg_total_ms':   fog_avg,
            'cloud_avg_total_ms': cloud_avg,
            'fog_p95_ms':         fog_p95,
            'cloud_p95_ms':       cloud_p95,
            'fog_p99_ms':         fog_p99,
            'cloud_p99_ms':       cloud_p99,
            'speedup_factor':     speedup,
            'verdict': (
                f'Fog is {speedup}× faster than Cloud' if speedup
                else 'Waiting for traffic data'
            ),
            'sdn_decision': (
                'SDN controller routes EMERGENCY/CRITICAL → Fog '
                f'({fog_avg}ms avg) to avoid Cloud delay ({cloud_avg}ms avg). '
                f'This is {speedup}× faster emergency response.'
                if speedup else
                'No traffic yet — both servers waiting for IoT packets.'
            ),
        },
        'timestamp': datetime.now().isoformat()
    }


@app.get("/dashboard")
async def dashboard():
    """Aggregated snapshot for the dashboard - one call gets everything."""
    async with aiohttp.ClientSession() as s:
        fog_stats_r, fog_alerts_r, cloud_stats_r, cloud_data_r, ryu_r, ryu_log_r, fog_m, cloud_m = \
            await asyncio.gather(
                fetch(s, f"{FOG_URL}/stats"),
                fetch(s, f"{FOG_URL}/alerts"),
                fetch(s, f"{CLOUD_URL}/stats"),
                fetch(s, f"{CLOUD_URL}/data"),
                fetch(s, f"{RYU_STATS_URL}/stats"),   # Ryu routing stats
                fetch(s, f"{RYU_STATS_URL}/routing-log"),  # Ryu routing log
                fetch(s, f"{FOG_URL}/metrics"),
                fetch(s, f"{CLOUD_URL}/metrics"),
            )

        # Fallback to proxy if Ryu unavailable (Mode 1)
        if ryu_r.get("error"):
            proxy_r = await fetch(s, f"{PROXY_URL}/stats")
            ryu_log_r = await fetch(s, f"{PROXY_URL}/routing-log")
        else:
            proxy_r = ryu_r

    fog_s   = fog_stats_r.get("stats",   {}) if isinstance(fog_stats_r,   dict) else {}
    cloud_s = cloud_stats_r.get("stats", {}) if isinstance(cloud_stats_r, dict) else {}
    proxy_s = proxy_r.get("stats",       {}) if isinstance(proxy_r,       dict) else {}

    alerts  = fog_alerts_r.get("alerts",   []) if isinstance(fog_alerts_r,  dict) else []
    records = cloud_data_r.get("records",  []) if isinstance(cloud_data_r,  dict) else []
    routing = ryu_log_r.get("events",      []) if isinstance(ryu_log_r,     dict) else []

    # Read proxy stats from nested dicts (by_node / by_class)
    by_node  = proxy_s.get("by_node",  {})
    by_class = proxy_s.get("by_class", {})

    # Latency comparison metrics (Fog vs Cloud — the core SDN justification)
    fog_total   = (fog_m.get('latency',   {}).get('total_ms',  {}) or {}) if isinstance(fog_m,   dict) else {}
    cloud_total = (cloud_m.get('latency', {}).get('total_ms',  {}) or {}) if isinstance(cloud_m, dict) else {}
    fog_proc    = (fog_m.get('latency',   {}).get('processing_ms', {}) or {}) if isinstance(fog_m,   dict) else {}
    cloud_proc  = (cloud_m.get('latency', {}).get('processing_ms', {}) or {}) if isinstance(cloud_m, dict) else {}

    fog_avg_total   = fog_total.get('avg_ms', 0)
    cloud_avg_total = cloud_total.get('avg_ms', 0)
    speedup = round(cloud_avg_total / fog_avg_total, 1) if fog_avg_total > 0 else None

    return {
        "summary": {
            # Fog stats
            "fog_alerts_total":    fog_s.get("total_alerts", 0),
            "fog_critical_count":  fog_s.get("critical_count", 0),
            "fog_avg_latency_ms":  fog_s.get("avg_response_time_ms", 0),

            # Cloud stats
            "cloud_batches_total": cloud_s.get("total_batches", 0),
            "cloud_data_points":   cloud_s.get("total_data_points", 0),
            "cloud_avg_latency_ms": cloud_s.get("avg_processing_time_ms", 0),

            # SDN Proxy stats — read from nested by_node / by_class dicts
            "sdn_total_packets":   proxy_s.get("total_packets", 0),
            "sdn_fog_routed":      by_node.get("fog", 0),
            "sdn_cloud_routed":    by_node.get("cloud", 0),
            "sdn_emergency_count": by_class.get("EMERGENCY", 0),
            "sdn_critical_count":  by_class.get("CRITICAL", 0),
            "sdn_analytics_count": by_class.get("ANALYTICS", 0),
            "sdn_bulk_count":      by_class.get("BULK", 0),
        },
        # ── Latency evaluation metrics ────────────────────────────────────────
        # This is the core evidence for why SDN+Fog computing is beneficial.
        # Emergency packets go to Fog (≪ 5ms) not Cloud (50–150ms).
        "latency_comparison": {
            "fog": {
                "avg_processing_ms":  fog_proc.get('avg_ms', 0),
                "avg_total_ms":       fog_avg_total,
                "p95_ms":             fog_total.get('p95_ms', 0),
                "p99_ms":             fog_total.get('p99_ms', 0),
                "samples":            fog_total.get('count', 0),
            },
            "cloud": {
                "avg_processing_ms":  cloud_proc.get('avg_ms', 0),
                "avg_total_ms":       cloud_avg_total,
                "p95_ms":             cloud_total.get('p95_ms', 0),
                "p99_ms":             cloud_total.get('p99_ms', 0),
                "samples":            cloud_total.get('count', 0),
            },
            "speedup_factor": speedup,
            "verdict": (
                f'Fog is {speedup}× faster than Cloud — '
                f'{fog_avg_total}ms vs {cloud_avg_total}ms avg total latency'
                if speedup else 'Waiting for traffic...'
            ),
        },
        "recent_alerts":    alerts[-5:],
        "recent_analytics": records[-5:],
        "recent_routing":   routing[-10:] if routing else [],
        "timestamp":        datetime.now().isoformat()
    }


def main():
    print("=" * 60)
    print("API GATEWAY v2 - SDN-IoT Unified Access Point")
    print("=" * 60)
    print(f"Fog Server  : {FOG_URL}")
    print(f"Cloud Server : {CLOUD_URL}")
    print(f"SDN Proxy   : {PROXY_URL}")
    print(f"Gateway     : http://localhost:{GATEWAY_PORT}")
    print(f"API Docs    : http://localhost:{GATEWAY_PORT}/docs")
    print("=" * 60)
    uvicorn.run(app, host=GATEWAY_HOST, port=GATEWAY_PORT, log_level="warning")


if __name__ == "__main__":
    main()
