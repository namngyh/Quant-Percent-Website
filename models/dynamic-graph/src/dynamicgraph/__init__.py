"""DynamicGraph - Dynamic Financial Network Model for VN30.

A statistical dynamic-graph system for the VN30 index and its constituents.
It describes the dependence structure between stocks, identifies central and
vulnerable nodes, tracks sector/community structure, measures market-wide
concentration and diversification decay, and evaluates whether the resulting
network features carry out-of-sample predictive value for VN30 stress.

The package is deliberately layered so that the explainable statistical core
runs without any optional dependency (torch, shap, optuna, leiden, ...).
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
