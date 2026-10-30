"""Backward-compatible import for the management dashboard blueprint."""

from controllers.admin import dashboard_bp

__all__ = ["dashboard_bp"]
