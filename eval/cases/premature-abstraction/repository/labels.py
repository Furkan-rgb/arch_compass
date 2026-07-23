def format_task_label(task_name: str) -> str:
    """Format a task name for the local task-list display."""
    return task_name.strip().replace("_", " ").title()
