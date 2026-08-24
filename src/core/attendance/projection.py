"""Compatibility facade for the former attendance projection module."""

from .application.projection import monthly_summary, project_days, today_summary

__all__ = ["monthly_summary", "project_days", "today_summary"]
