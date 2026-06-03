"""Pydantic schemas for the structured summary report.

Implemented in M4. The LLM is instructed to return JSON matching ``SummaryReport``,
which is then validated with Pydantic (with retries on malformed output).
"""
