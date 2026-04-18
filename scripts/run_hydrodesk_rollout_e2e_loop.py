#!/usr/bin/env python3
"""
HydroDesk rollout E2E loop generic entrypoint.

This is the product-facing alias for `run_hydrodesk_six_case_e2e_loop.py`.
The current rollout may happen to use six validation cases, but the platform
boundary is the manifest-driven rollout cohort, not the number of cases.
"""
from __future__ import annotations

from run_hydrodesk_six_case_e2e_loop import main


if __name__ == "__main__":
    raise SystemExit(main())
