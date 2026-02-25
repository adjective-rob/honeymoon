"""
GLITCHLAB Auditor

Scans a repository for actionable findings and generates
well-scoped GLITCHLAB task YAML files.

Usage:
    glitchlab audit --repo ~/Desktop/Zephyr
    glitchlab audit --repo ~/Desktop/Zephyr --kind missing_doc
    glitchlab audit --repo ~/Desktop/Zephyr --dry-run
"""

from .scanner import Scanner, ScanResult, Finding
from .task_writer import TaskWriter, group_findings_into_tasks

__all__ = ["Scanner", "ScanResult", "Finding", "TaskWriter", "group_findings_into_tasks"]