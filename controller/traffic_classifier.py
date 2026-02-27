#!/usr/bin/env python3
"""
Traffic Classifier — Shared Intelligence Module
================================================
Used by BOTH the standalone SDN Proxy AND the Ryu SDN Controller.

Classifies IoT data purely based on CONTENT (payload inspection).
No device needs to know its destination. The network decides.

Classification Priority (highest → lowest):
  1. EMERGENCY  → payload content signals life-safety event
  2. CRITICAL   → high-urgency sensor readings above thresholds
  3. BULK       → large payload, low-priority batch data
  4. ANALYTICS  → default, periodic sensor readings
"""

import json
import logging

logger = logging.getLogger("TrafficClassifier")


# ── Thresholds (tunable — no hardcoded ports/IPs here) ─────────────────────
THRESHOLDS = {
    "smoke_level_critical":  50,    # % — above this → CRITICAL
    "smoke_level_emergency": 80,    # % — above this → EMERGENCY
    "temperature_high":      45.0,  # °C — dangerously high
    "temperature_low":        0.0,  # °C — dangerously low
    "air_quality_hazardous": 150,   # AQI — hazardous level
    "bulk_payload_bytes":   4096,   # bytes — large payload = BULK
    "bulk_data_points":       20,   # count — many points = BULK
}

# ── Traffic Classes ─────────────────────────────────────────────────────────
class TrafficClass:
    EMERGENCY = "EMERGENCY"    # Immediate danger — Fog
    CRITICAL  = "CRITICAL"     # High urgency — Fog
    ANALYTICS = "ANALYTICS"    # Normal readings — Cloud
    BULK      = "BULK"         # Heavy batch data — Cloud


# ── Classifier ──────────────────────────────────────────────────────────────
class TrafficClassifier:
    """
    Classifies IoT payloads by inspecting their CONTENT.

    Decision is made purely on what the data contains — not which port
    it arrived on, not which device sent it.
    """

    def classify(self, payload_bytes: bytes) -> dict:
        """
        Main entry point. Accepts raw bytes, returns a classification result.

        Returns:
            {
                "traffic_class": "CRITICAL",
                "destination":   "FOG",
                "reason":        "Smoke level 85% exceeds emergency threshold",
                "confidence":    0.95,
                "data":          { ... parsed payload ... }
            }
        """
        result = {
            "traffic_class": TrafficClass.ANALYTICS,
            "destination":   "CLOUD",
            "reason":        "Default: periodic analytics data",
            "confidence":    0.5,
            "data":          {}
        }

        # ── Step 1: Parse payload ───────────────────────────────────────────
        try:
            data = json.loads(payload_bytes.decode("utf-8"))
            result["data"] = data
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            result["reason"] = f"Unparseable payload — defaulting to ANALYTICS"
            logger.warning(f"[Classifier] Could not parse payload: {e}")
            return result

        # ── Step 2: Run classification rules (priority order) ───────────────
        classification = self._run_rules(data, len(payload_bytes))
        result.update(classification)

        logger.info(
            f"[Classifier] {result['traffic_class']} → {result['destination']} | "
            f"Reason: {result['reason']}"
        )
        return result

    def _run_rules(self, data: dict, payload_size: int) -> dict:
        """Apply classification rules in priority order."""

        # ── Rule 1: EMERGENCY — fire/smoke above danger threshold ───────────
        smoke = data.get("smoke_level", 0)
        if smoke >= THRESHOLDS["smoke_level_emergency"]:
            return {
                "traffic_class": TrafficClass.EMERGENCY,
                "destination":   "FOG",
                "reason":        f"Smoke level {smoke}% ≥ emergency threshold ({THRESHOLDS['smoke_level_emergency']}%)",
                "confidence":    0.99,
            }

        # ── Rule 2: CRITICAL — fire/smoke above critical threshold ──────────
        if smoke >= THRESHOLDS["smoke_level_critical"]:
            return {
                "traffic_class": TrafficClass.CRITICAL,
                "destination":   "FOG",
                "reason":        f"Smoke level {smoke}% ≥ critical threshold ({THRESHOLDS['smoke_level_critical']}%)",
                "confidence":    0.95,
            }

        # ── Rule 3: CRITICAL — sensor status explicitly marks emergency ──────
        status = data.get("status", "").upper()
        if status in ("ALARM", "EMERGENCY", "DANGER"):
            return {
                "traffic_class": TrafficClass.CRITICAL,
                "destination":   "FOG",
                "reason":        f"Sensor status='{status}' signals critical event",
                "confidence":    0.92,
            }

        # ── Rule 4: CRITICAL — temperature out of safe range ────────────────
        temp = data.get("value") if data.get("data_type") == "temperature" else None
        if temp is not None:
            if temp >= THRESHOLDS["temperature_high"] or temp <= THRESHOLDS["temperature_low"]:
                return {
                    "traffic_class": TrafficClass.CRITICAL,
                    "destination":   "FOG",
                    "reason":        f"Temperature {temp}°C is outside safe range",
                    "confidence":    0.90,
                }

        # ── Rule 5: CRITICAL — air quality hazardous ────────────────────────
        aqi = data.get("air_quality_index", 0)
        if aqi >= THRESHOLDS["air_quality_hazardous"]:
            return {
                "traffic_class": TrafficClass.CRITICAL,
                "destination":   "FOG",
                "reason":        f"AQI={aqi} is hazardous (≥{THRESHOLDS['air_quality_hazardous']})",
                "confidence":    0.88,
            }

        # ── Rule 6: BULK — large payload size ───────────────────────────────
        num_points = len(data.get("data_points", []))
        if num_points >= THRESHOLDS["bulk_data_points"] or \
           payload_size >= THRESHOLDS["bulk_payload_bytes"]:
            return {
                "traffic_class": TrafficClass.BULK,
                "destination":   "CLOUD",
                "reason":        f"Bulk data: {num_points} points, {payload_size} bytes",
                "confidence":    0.85,
            }

        # ── Rule 7: ANALYTICS — everything else ─────────────────────────────
        return {
            "traffic_class": TrafficClass.ANALYTICS,
            "destination":   "CLOUD",
            "reason":        f"Periodic sensor data — no urgency detected",
            "confidence":    0.75,
        }
