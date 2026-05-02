"""
HONEYMOON Auditor

Scans a repository for actionable findings and generates
well-scoped HONEYMOON task YAML files.

Usage:
    honeymoon audit --repo ~/Desktop/Zephyr
    honeymoon audit --repo ~/Desktop/Zephyr --kind missing_doc
    honeymoon audit --repo ~/Desktop/Zephyr --dry-run
"""

from .scanner import Scanner, ScanResult, Finding
from .task_writer import TaskWriter, group_findings_into_tasks

__all__ = ["Scanner", "ScanResult", "Finding", "TaskWriter", "group_findings_into_tasks"]