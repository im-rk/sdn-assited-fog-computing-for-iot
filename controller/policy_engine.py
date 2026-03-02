#!/usr/bin/env python3
"""
Policy Engine - SDN Routing Rule Evaluator

Loads routing rules from a JSON config file and evaluates
incoming IoT packets to determine destination node (fog/cloud).
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("PolicyEngine")

# Locate policy file relative to this file's directory
POLICY_FILE = Path(__file__).parent.parent / "config" / "routing_policy.json"


class PolicyEngine:
    """Evaluates IoT packets against policy rules to determine routing destination."""

    def __init__(self, policy_path: str = None):
        self.policy_path = policy_path or str(POLICY_FILE)
        self.policy      = {}
        self.nodes       = {}
        self.rules       = []
        self.load_policy()


    def load_policy(self):
        """Load and parse the routing policy from JSON."""
        with open(self.policy_path, "r") as f:
            self.policy = json.load(f)

        self.nodes = {
            k: v for k, v in self.policy["nodes"].items()
            if isinstance(v, dict)
        }
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
        try:
            data = json.loads(payload_bytes.decode("utf-8"))
        except Exception:
            data = {}
            logger.warning("Could not parse payload — applying default rule")

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

    def _matches(self, conditions: list, data: dict) -> bool:
        """All conditions must match (AND logic). Supports: ==, !=, >=, <=, >, <, in, not_in, exists."""
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
