"""Constants for the Tasks integration."""
DOMAIN = "tasks"

# Config keys
CONF_URL = "url"
CONF_REFRESH_INTERVAL = "refresh_interval"
CONF_CREATE_PROJECT_LISTS = "create_project_lists"
CONF_SHOW_DUE_IN = "show_due_in"
CONF_CALENDAR_DATE_FIELD = "calendar_date_field"

# Kanban stages (mirrors tasks_go server)
STAGE_SOMEDAY = "someday"
STAGE_UPCOMING = "upcoming"
STAGE_READY = "ready"
STAGE_IN_PROGRESS = "in_progress"
STAGE_DONE = "done"

STAGES = [STAGE_SOMEDAY, STAGE_UPCOMING, STAGE_READY, STAGE_IN_PROGRESS, STAGE_DONE]
# Stages that hold active (not-yet-completed) work — what /api/board returns.
ACTIVE_STAGES = [STAGE_SOMEDAY, STAGE_UPCOMING, STAGE_READY, STAGE_IN_PROGRESS]
# New todo items land here unless a project list says otherwise.
DEFAULT_STAGE = STAGE_UPCOMING

# Defaults
DEFAULT_REFRESH_INTERVAL = 900  # seconds - 15 minutes
DEFAULT_SHOW_DUE_IN = 7  # days
DEFAULT_CALENDAR_DATE_FIELD = "due"  # "due" or "deadline"

API_TIMEOUT = 10  # seconds
