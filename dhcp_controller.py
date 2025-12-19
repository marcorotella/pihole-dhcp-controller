import os
import requests
import time
import logging
from typing import NamedTuple, List
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PiholeInstance(NamedTuple):
    name: str
    ip: str
    token: str
    is_online: bool = False

# --- Configuration from Environment Variables ---
def get_config() -> List[PiholeInstance]:
    """Retrieves and validates the configuration from the environment."""
    
    # Primary and Secondary are required
    primary_ip = os.getenv('PRIMARY_PIHOLE_IP')
    primary_token = os.getenv('PRIMARY_PIHOLE_TOKEN')
    secondary_ip = os.getenv('SECONDARY_PIHOLE_IP')
    secondary_token = os.getenv('SECONDARY_PIHOLE_TOKEN')

    if not all([primary_ip, primary_token, secondary_ip, secondary_token]):
        logging.error("Error: Ensure that IP and TOKEN are set for at least the PRIMARY and SECONDARY servers.")
        exit(1)
    
    piholes = [
        PiholeInstance(name='Primary', ip=primary_ip, token=primary_token),
        PiholeInstance(name='Secondary', ip=secondary_ip, token=secondary_token),
    ]

    # Tertiary is optional
    tertiary_ip = os.getenv('TERTIARY_PIHOLE_IP')
    tertiary_token = os.getenv('TERTIARY_PIHOLE_TOKEN')

    if tertiary_ip and tertiary_token:
        piholes.append(PiholeInstance(name='Tertiary', ip=tertiary_ip, token=tertiary_token))
        logging.info("Detected configuration for 3 servers (Primary, Secondary, Tertiary).")
    else:
        logging.info("Detected configuration for 2 servers (Primary, Secondary). Tertiary server is ignored.")

    return piholes

CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))

def check_host_status(pihole: PiholeInstance) -> bool:
    """Checks if a Pi-hole instance is reachable."""
    base_url = pihole.ip
    if not base_url.startswith(('http://', 'https://')):
        base_url = 'http://' + base_url
    
    final_url = f"{base_url.rstrip('/')}/admin/"

    try:
        response = requests.get(final_url, timeout=5)
        response.raise_for_status()
        logging.info(f"OK: {pihole.name} Pi-hole ({pihole.ip}) is online.")
        return True
    except (requests.exceptions.RequestException) as e:
        logging.warning(f"FAIL: {pihole.name} Pi-hole ({pihole.ip}) is not reachable. Error: {e}")
        return False

def set_dhcp_status(pihole: PiholeInstance, enable: bool):
    """Enables or disables DHCP on a specific Pi-hole instance."""
    if not pihole.is_online:
        logging.info(f"SKIP: {pihole.name} is offline, cannot change DHCP status.")
        return

    action = "enable" if enable else "disable"
    
    base_url = pihole.ip
    if not base_url.startswith(('http://', 'https://')):
        base_url = 'http://' + base_url

    url = f"{base_url.rstrip('/')}/admin/api.php"
    
    try:
        params = {"auth": pihole.token, action: "dhcp"}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data.get("status") == f"dhcp_{action}d":
            logging.info(f"SUCCESS: DHCP {action}d on {pihole.name} ({pihole.ip}).")
        else:
            logging.info(f"INFO: DHCP status on {pihole.name} was already {action}d. No changes made.")
            
    except (requests.exceptions.RequestException, ValueError) as e:
        logging.error(f"ERROR: Could not change DHCP status on {pihole.name}. Error: {e}")

def main_loop():
    """Main loop that orchestrates the DHCP status of the servers."""
    logging.info("DHCP controller service started.")
    
    piholes = get_config()

    while True:
        logging.info("--- Starting new check cycle ---")
        
        # 1. Check the status of all Pi-holes
        online_piholes = [p._replace(is_online=check_host_status(p)) for p in piholes]
        
        # 2. Determine which server should be the DHCP master (the first one online in the list)
        active_dhcp_server = next((p for p in online_piholes if p.is_online), None)
        
        if active_dhcp_server:
            logging.info(f"DECISION: {active_dhcp_server.name} ({active_dhcp_server.ip}) will be the active DHCP server.")
        else:
            logging.warning("WARNING: No Pi-hole is online. Cannot enable a DHCP server.")

        # 3. Apply the decision: enable on the master, disable on all others
        for p in online_piholes:
            if p == active_dhcp_server:
                set_dhcp_status(p, enable=True) # Enable the master
            else:
                set_dhcp_status(p, enable=False) # Disable the others
        
        logging.info(f"--- Check cycle complete. Next check in {CHECK_INTERVAL} seconds. ---")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main_loop()
