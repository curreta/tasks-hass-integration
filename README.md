# Tasks — Home Assistant integration

Syncs a `tasks_go` kanban board (a self-hosted, VTODO-based personal task
server) into Home Assistant. Modeled on the Donetick HA integration, but tuned
for the tasks_go backend: no auth, kanban stages, projects instead of
assignees, and no recurrence.

## What it exposes

- **To-do lists**
  - `todo.tasks` — every active (not-done) task across all stages and projects.
  - `todo.tasks_<project>` — one list per project (optional; enable in options).
  - Checking an item off completes it on the server; adding one creates it in the
    `upcoming` stage.
- **Sensors**
  - `sensor.tasks_someday` / `tasks_upcoming` / `tasks_ready` / `tasks_in_progress`
    — count per stage, with the item list as an attribute.
  - `sensor.tasks_due_today` — count of tasks due today or overdue.
  - `sensor.tasks_next_due` — timestamp of the soonest due date.
- **Calendar**
  - `calendar.tasks` — each task's due date (or deadline) as a one-day event.

## Services

| Service | Purpose |
|---|---|
| `tasks.create_task` | Create a task (summary, stage, project, due, deadline, priority, tags) |
| `tasks.update_task` | Update fields on a task by ID |
| `tasks.complete_task` | Mark a task complete |
| `tasks.delete_task` | Delete a task |
| `tasks.move_task` | Move a task to another kanban stage |

## Installation (HACS)

1. HACS → ⋮ → **Custom repositories**.
2. Add `https://github.com/curreta/tasks-hass-integration`, category **Integration**.
3. Install **Tasks**, then restart Home Assistant.
4. **Settings → Devices & Services → Add Integration → Tasks**.
5. Enter the server URL.

### Server URL

Point at an address Home Assistant can actually reach. The tasks_go server
binds `:8274` on the LAN and (optionally) `https://tasks.<tailnet>.ts.net` over
Tailscale. Use the Tailscale name only if the HA host is on the tailnet;
otherwise use the LAN address, e.g. `http://<server-host>:8274`.

The server requires no authentication.

## Options

- **Create a to-do list per project** — off by default.
- **Days ahead to consider "due soon"** — reserved for dashboards.
- **Calendar date source** — `due` (default) or `deadline`.
- **Refresh interval** — default 15 minutes.

## Development

This is a standard HA custom component under `custom_components/tasks/`. Copy
that directory into `config/custom_components/` to test a working copy without
HACS, then restart Home Assistant.
