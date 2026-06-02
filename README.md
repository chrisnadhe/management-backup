# Network Management Backup App

A comprehensive network configuration backup solution built with FastAPI, HTMX, Tailwind CSS, and Netmiko.

This application has been fully refactored to use **HTMX** for dynamic, SPA-like frontend operations and features a premium **modern slate-and-indigo user interface** with Outfit typography, glassmorphism, and custom micro-interactions.

---

## Features

- **Interactive SPA-like Navigation**: Boosted links (`hx-boost`) swap page contents dynamically without full browser refreshes.
- **Asynchronous Modal Forms**: Creation (Add) and editing (Edit) of resources are loaded dynamically inside modal overlays and saved asynchronously.
- **Animated Deletions with Transitions**: Row-level actions like deletes prompt with a custom confirmation modal and fade-out smoothly using CSS transitions before removal from the DOM.
- **Real-Time Polling & Statuses**: Running backups display animated spinners and poll the server automatically every 2 seconds, updating their state badges dynamically.
- **Live Terminal Log Streaming**: Expandable console logs and the log viewer page stream raw Netmiko SSH interactions in real-time while backups are running.
- **Active Search & Inline Filtering**: Search inputs filter Devices, Backups, and Logs in real-time with a debounced 300ms delay.
- **Dynamic Toast Alerts**: Submitting forms or triggering backups dispatches custom `HX-Trigger` headers from the backend to display slide-in notification banners.
- **Robust Backup Scheduler**: Schedules automated backups targeting specific devices or entire groups using standard Unix cron expressions.

---

## Prerequisites

- Python 3.12+
- [UV](https://github.com/astral-sh/uv) (recommended)

---

## Installation

1. Clone the repository (or navigate to the directory).
2. Install dependencies:
   ```bash
   uv sync
   ```

---

## Running the Application

Start the server using `uv`:
```bash
uv run uvicorn app.main:app --reload
```

Access the application at: [http://localhost:8000](http://localhost:8000)

---

## Initialization

When you run the application for the first time:
- A **SQLite database** (`network_backup.db`) will be automatically created in the root directory.
- A **`backups/` folder** will be created automatically when the first backup is executed to store configuration files and session logs.

There is no need for manual database setup.

---

## Usage

1. **Add Credentials**: Go to "Credentials" and add SSH login details.
2. **Add Commands**: Define backup commands (e.g., `show running-config` for Cisco IOS).
3. **Add Devices**: Register your network devices and assign credentials.
4. **Run Backup**: Go to "Backups" and trigger a backup manually, or set up a Schedule.

---

## License

MIT