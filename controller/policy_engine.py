#!/usr/bin/env python3
"""
Policy Engine — Generic SDN Rule Executor
==========================================
Loads routing rules from config/routing_policy.json at startup.
Evaluates any IoT packet against those rules.
Routes to whichever node the policy says.

This code contains ZERO hardcoded IPs, ports, or thresholds.
Everything is driven by the JSON policy file.

To change routing behaviour:
    → Edit config/routing_policy.json
    → Restart the proxy
    → No code changes needed
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("PolicyEngine")

# Locate policy file relative to this file's directory
POLICY_FILE = Path(__file__).parent.parent / "config" / "routing_policy.json"


class PolicyEngine:
    """
    Generic rule executor.
    Knows nothing about fire alarms, fog, cloud, or any domain concept.
    It only knows how to evaluate rules from the policy file.
    """

    def __init__(self, policy_path: str = None):
        self.policy_path = policy_path or str(POLICY_FILE)
        self.policy      = {}
        self.nodes       = {}
        self.rules       = []
        self.load_policy()

    # ── Policy Loading ────────────────────────────────────────────────────────
    def load_policy(self):
        """Load and parse the routing policy from JSON."""
        with open(self.policy_path, "r") as f:
            self.policy = json.load(f)

        self.nodes = self.policy["nodes"]
        # Sort rules by priority descending — highest priority evaluated first
        self.rules = sorted(
            self.policy["rules"],
            key=lambda r: r["priority"],
            reverse=True
        )

        logger.info(
            f"Policy loaded: '{self.policy['policy_name']}' | "
            f"{len(self.rules)} rules | {len(self.nodes)} nodes"
        )
        for node_name, node_cfg in self.nodes.items():
            logger.info(f"  Node '{node_name}' → {node_cfg['host']}:{node_cfg['port']}")

    def reload_policy(self):
        """Hot-reload policy — no restart needed."""
        logger.info("Reloading policy...")
        self.load_policy()

    # ── Core Evaluation ───────────────────────────────────────────────────────
    def evaluate(self, payload_bytes: bytes) -> dict:
        """
        Evaluate raw packet bytes against all policy rules.

        Returns:
            {
                "rule_id":       "R001",
                "rule_name":     "Emergency smoke level",
                "traffic_class": "EMERGENCY",
                "node_name":     "fog",
                "node":          { "host": "127.0.0.1", "port": 5001, ... },
                "reason":        "Rule R001: smoke_level 85 >= 80",
                "data":          { ...parsed payload... }
            }
        """
        # ── Step 1: Parse payload ─────────────────────────────────────────────
        try:
            data = json.loads(payload_bytes.decode("utf-8"))
        except Exception:
            data = {}
            logger.warning("Could not parse payload — applying default rule")

        # ── Step 2: Find first matching rule (highest priority) ───────────────
        for rule in self.rules:
            if self._matches(rule["conditions"], data):
                node_name = rule["action"]["route_to"]
                return {
                    "rule_id":       rule["id"],
                    "rule_name":     rule["name"],
                    "traffic_class": rule["action"]["traffic_class"],
                    "node_name":     node_name,
                    "node":          self.nodes[node_name],
                    "reason":        self._format_reason(rule, data),
                    "data":          data
                }

        # Should never reach here since the default rule has priority=0
        default_node = list(self.nodes.values())[0]
        return {
            "rule_id": "DEFAULT", "rule_name": "Fallback",
            "traffic_class": "ANALYTICS", "node_name": list(self.nodes.keys())[0],
            "node": default_node, "reason": "No rule matched", "data": data
        }

    # ── Condition Evaluator ───────────────────────────────────────────────────
    def _matches(self, conditions: list, data: dict) -> bool:
        """
        All conditions in a rule must match (AND logic).
        Supports operators: ==, !=, >=, <=, >, <, in, not_in, exists
        """
        for cond in conditions:
            field    = cond["field"]
            operator = cond["operator"]
            expected = cond["value"]
            actual   = data.get(field)

            if actual is None:
                return False

            if   operator == "==":      matched = actual == expected
            elif operator == "!=":      matched = actual != expected
            elif operator == ">=":      matched = actual >= expected
            elif operator == "<=":      matched = actual <= expected
            elif operator == ">":       matched = actual >  expected
            elif operator == "<":       matched = actual <  expected
            elif operator == "in":      matched = actual in expected
            elif operator == "not_in":  matched = actual not in expected
            elif operator == "exists":  matched = field in data
            else:
                logger.warning(f"Unknown operator '{operator}' — skipping condition")
                matched = True

            if not matched:
                return False

        return True   # All conditions matched (or rule has no conditions = default)

    def _format_reason(self, rule: dict, data: dict) -> str:
        """Build a human-readable explanation of why this rule matched."""
        if not rule["conditions"]:
            return f"Rule {rule['id']}: {rule['name']} (default)"

        cond_strs = []
        for cond in rule["conditions"]:
            actual = data.get(cond["field"], "N/A")
            cond_strs.append(f"{cond['field']}={actual} {cond['operator']} {cond['value']}")

        return f"Rule {rule['id']} [{rule['name']}]: {' AND '.join(cond_strs)}"

    def get_collection_endpoint(self) -> tuple:
        """Return (host, port) for the single collection endpoint."""
        ep = self.policy["collection_endpoint"]
        return ep["host"], ep["port"]

    def get_node(self, name: str) -> dict:
        """Return node config by name."""
        return self.nodes[name]
