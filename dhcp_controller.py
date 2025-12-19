import os
import requests
import time
import logging
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PiholeInstance:
    """A mutable class to hold the state of a Pi-hole instance, including the session ID."""
    def __init__(self, name: str, ip: str, token: str):
        self.name = name
        self.ip = ip
        self.token = token  # This is the web password
        self.is_online = False
        self.sid: Optional[str] = None

def get_config() -> List[PiholeInstance]:
    """Retrieves and validates the configuration from the environment."""
    primary_ip = os.getenv('PRIMARY_PIHOLE_IP')
    primary_token = os.getenv('PRIMARY_PIHOLE_TOKEN')
    secondary_ip = os.getenv('SECONDARY_PIHOLE_IP')
    secondary_token = os.getenv('SECONDARY_PIHOLE_TOKEN')

    if not all([primary_ip, primary_token, secondary_ip, secondary_token]):
        logging.error("Error: Ensure that IP and Password are set for at least the PRIMARY and SECONDARY servers.")
        exit(1)
    
    piholes = [
        PiholeInstance(name='Primary', ip=primary_ip, token=primary_token),
        PiholeInstance(name='Secondary', ip=secondary_ip, token=secondary_token),
    ]

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
        requests.get(final_url, timeout=5).raise_for_status()
        pihole.is_online = True
        logging.info(f"OK: {pihole.name} ({pihole.ip}) is online.")
        return True
    except requests.exceptions.RequestException as e:
        pihole.is_online = False
        logging.warning(f"FAIL: {pihole.name} ({pihole.ip}) is not reachable. Error: {e}")
        return False

def authenticate(pihole: PiholeInstance) -> bool:
    """Authenticates with a Pi-hole instance to get and store a session ID (SID)."""
    if not pihole.is_online:
        return False

    base_url = pihole.ip.rstrip('/')
    auth_url = f"{base_url}/api/auth"
    auth_payload = {"password": pihole.token}
    
    try:
        logging.info(f"Authenticating with {pihole.name} to get session ID...")
        auth_resp = requests.post(auth_url, json=auth_payload, timeout=10)
        auth_resp.raise_for_status()
        
        sid = auth_resp.json().get("session", {}).get("sid")
        if not sid:
            logging.error(f"Authentication response from {pihole.name} did not contain a valid 'sid'. Full response: {auth_resp.json()}")
            return False
        
        pihole.sid = sid
        logging.info(f"Successfully obtained and stored new session ID for {pihole.name}.")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"ERROR: Authentication request failed for {pihole.name}. Error: {e}")
        pihole.sid = None
        return False

def set_dhcp_status(pihole: PiholeInstance, enable: bool):
    """Enables or disables DHCP, handling authentication and session reuse."""
    if not pihole.is_online:
        return

    # Authenticate only if we don't have a session ID
    if not pihole.sid:
        if not authenticate(pihole):
            logging.error(f"Cannot set DHCP status for {pihole.name} due to authentication failure.")
            return

    action_status = "enabled" if enable else "disabled"
    base_url = pihole.ip.rstrip('/')
    config_url = f"{base_url}/api/config?restart=true"
    
    headers = {
        "X-Api-Key": pihole.sid,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    config_payload = {"config": {"dhcp": {"active": enable}}}

    try:
        logging.info(f"Attempting to set DHCP on {pihole.name} to {action_status} using session ID...")
        response = requests.patch(config_url, headers=headers, json=config_payload, timeout=15)
        response.raise_for_status()
        
        if response.json().get("success"):
            logging.info(f"SUCCESS: DHCP on {pihole.name} set to {action_status}.")
        else:
            logging.warning(f"INFO: API call succeeded but did not report success. API response: {response.json()}")

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            logging.warning(f"Session ID for {pihole.name} has expired. Will re-authenticate on the next cycle.")
            pihole.sid = None # Invalidate the SID
        else:
            logging.error(f"ERROR: Could not change DHCP status on {pihole.name}. Error: {e}")
    except (requests.exceptions.RequestException, ValueError) as e:
        logging.error(f"ERROR: Could not change DHCP status on {pihole.name}. Error: {e}")

def main_loop():
    """Main loop that orchestrates the DHCP status of the servers."""
    logging.info("DHCP controller service started.")
    
    piholes = get_config()

    while True:
        logging.info("--- Starting new check cycle ---")
        
        # 1. Check the status of all Pi-holes
        for p in piholes:
            check_host_status(p)
        
        # 2. Determine which server should be the DHCP master
        active_dhcp_server = next((p for p in piholes if p.is_online), None)
        
        if active_dhcp_server:
            logging.info(f"DECISION: {active_dhcp_server.name} ({active_dhcp_server.ip}) will be the active DHCP server.")
        else:
            logging.warning("WARNING: No Pi-hole is online. Cannot enable a DHCP server.")

        # 3. Apply the decision
        for p in piholes:
            set_dhcp_status(p, enable=(p == active_dhcp_server))
        
        logging.info(f"--- Check cycle complete. Next check in {CHECK_INTERVAL} seconds. ---")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main_loop()
