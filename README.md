# Pi-hole DHCP Controller

This project implements a centralized failover and failback system for managing the DHCP server across multiple Pi-hole instances (two or three). The controller monitors the health status of all configured Pi-holes and ensures that the DHCP server is active only on the highest-priority instance that is currently online, preventing DHCP conflicts and ensuring service continuity.

## Features

*   **Centralized Control:** A single service manages the DHCP status of all your Pi-hole instances.
*   **Hierarchical Failover Logic:** Defines a priority among servers (Primary > Secondary > Tertiary). DHCP will only be active on the highest-priority server that is reachable.
*   **Automatic Failback:** If a higher-priority server comes back online, it automatically resumes the role of the DHCP server, disabling DHCP on other servers.
*   **Flexible Support (2 or 3 servers):** The script automatically detects whether you are using two or three Pi-hole servers based on your configuration.
*   **Simple Configuration:** All settings are managed through a `.env` file.
*   **Deploy with Docker Compose:** Easy to install and manage via Docker Compose on a dedicated VM.

## Prerequisites

*   **Docker and Docker Compose:** Installed on the VM that will host the controller service.
*   **Functional Pi-hole Instances (v6.0+):** All Pi-holes must be configured and accessible over the network from the controller's VM.
*   **Pi-hole App Passwords:** For each Pi-hole instance, you must create a dedicated App Password with write permissions (see [Pi-hole v6 Setup](#pi-hole-v6-setup)).

## Pi-hole v6 Setup

Pi-hole v6 introduced a more secure API that requires **App Passwords** for third-party integrations. To allow this controller to change DHCP settings, follow these steps for **each** Pi-hole instance:

1.  Log in to your Pi-hole web interface.
2.  Navigate to **Settings** > **API**.
3.  Scroll down to the **App Passwords** section.
4.  Click **Add new password**.
5.  Give it a name (e.g., `DHCP-Controller`).
6.  **Crucial:** Check the box for **"App sudo"** (or "Write access" / "Full control"). Without this, the controller will be able to read the status but **cannot** enable or disable the DHCP server.
7.  Save and **copy the generated password**. You will need this for your `.env` file.

## Installation and Configuration

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/marcorotella/pihole-dhcp-controller.git
    cd pihole-dhcp-controller
    ```

2.  **Create the `.env` configuration file:**
    *   Copy the `.env.example` file to `.env`:
        ```bash
        cp .env.example .env
        ```
    *   Open the `.env` file with a text editor and fill in the variables:
        ```ini
        # --- Pi-hole DHCP Controller Configuration ---

        # Check interval in seconds
        CHECK_INTERVAL=60

        # --- Primary Pi-hole (Priority 1 - Required) ---
        PRIMARY_PIHOLE_IP=YOUR_PRIMARY_IP
        # Use the App Password generated in the Pi-hole UI
        PRIMARY_PIHOLE_TOKEN=YOUR_PRIMARY_APP_PASSWORD

        # --- Secondary Pi-hole (Priority 2 - Required) ---
        SECONDARY_PIHOLE_IP=YOUR_SECONDARY_IP
        SECONDARY_PIHOLE_TOKEN=YOUR_SECONDARY_APP_PASSWORD

        # --- Tertiary Pi-hole (Priority 3 - Optional) ---
        # Leave these two variables empty or comment them out for a 2-server setup.
        TERTIARY_PIHOLE_IP=
        TERTIARY_PIHOLE_TOKEN=
        ```
    *   **Important:** Make sure to use the **App Passwords** (not your login password) and ensure they have **app_sudo** enabled.

3.  **Start the Service with Docker Compose:**
    *   From the same directory where `docker-compose.yml` and `.env` are located, run:
        ```bash
        docker-compose up -d --build
        ```
    *   This command will build the Docker image (if not already built or if there are changes) and start the service in the background.

## How It Works

The `dhcp_controller` runs a check cycle every `CHECK_INTERVAL` seconds:

1.  **Check the status of all Pi-holes:** It checks the reachability of the Primary, Secondary, and Tertiary (if configured) servers.
2.  **Determine the Active DHCP Server:**
    *   If the **Primary** is online, it will be the active DHCP server.
    *   Otherwise, if the **Secondary** is online, it will be the active DHCP server.
    *   Otherwise, if the **Tertiary** is online, it will be the active DHCP server.
    *   If no Pi-hole is online, no DHCP server will be activated.
3.  **Apply Changes:**
    *   It enables DHCP on the server chosen as "active".
    *   It disables DHCP on all other online servers.

This logic ensures that the DHCP service is always managed by the highest-priority available server and allows for automatic service restoration on the primary server as soon as it comes back online.

## Monitoring

To monitor the controller's operation and view logs in real-time:

```bash
docker-compose logs -f
```
