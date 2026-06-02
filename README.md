# Network Management Backup App

A comprehensive network configuration backup solution built with FastAPI, HTMX, Tailwind CSS, and Netmiko.

## Features

-   **Device Management**: Add/Edit/Delete network devices (Cisco, Juniper, Arista, etc.).
-   **Credential Management**: Securely manage device credentials.
-   **Command Management**: Define commands to execute for backups.
-   **Automated Backups**: Schedule backups using Cron expressions.
-   **Manual Backups**: Trigger backups on-demand.
-   **Backup History**: View logs and download backup files.
-   **Dashboard**: Overview of system status.

## Prerequisites

-   Python 3.12+
-   [UV](https://github.com/astral-sh/uv) (recommended)

## Installation

1.  Clone the repository (or navigate to the directory).
2.  Install dependencies:
    ```bash
    uv sync
    ```

## Running the Application

Start the server using `uv`:

```bash
uv run uvicorn app.main:app --reload
```

Access the application at: [http://localhost:8000](http://localhost:8000)

## Initialization

When you run the application for the first time:

-   A **SQLite database** (`network_backup.db`) will be automatically created in the root directory.
-   A **`backups/` folder** will be created automatically when the first backup is executed to store configuration files and session logs.

There is no need for manual database setup.

## Usage

1.  **Add Credentials**: Go to "Credentials" and add SSH login details.
2.  **Add Commands**: Define backup commands (e.g., `show running-config` for Cisco IOS).
3.  **Add Devices**: Register your network devices and assign credentials.
4.  **Run Backup**: Go to "Backups" and trigger a backup manually, or set up a Schedule.
