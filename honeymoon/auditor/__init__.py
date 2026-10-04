"""
HONEYMOON Auditor

Scans a repository for actionable findings and generates
well-scoped HONEYMOON task YAML files.

Usage:
    honeymoon audit --repo ~/my-project
    honeymoon audit --repo ~/my-project --kind missing_doc
    honeymoon audit --repo ~/my-project --dry-run
"""

from .scanner import Scanner, ScanResult, Finding
from .task_writer import TaskWriter, group_findings_into_tasks

__all__ = ["Scanner", "ScanResult", "Finding", "TaskWriter", "group_findings_into_tasks"]