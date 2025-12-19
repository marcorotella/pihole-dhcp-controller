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
    """A mutable class to hold the state of a Pi-hole instance, ensuring session reuse."""
    def __init__(self, name: str, ip: str, token: str):
        self.name = name
        self.ip = ip
        self.token = token  # Web interface password
        self.is_online = False
        self.session = requests.Session()
        self.sid: Optional[str] = None
        self.csrf: Optional[str] = None
        
        # Prepare the base URL and Referer
        base_url = self.ip
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'http://' + base_url
        self.base_url = base_url.rstrip('/')
        self.referer = self.base_url + "/"
        
        # Set default headers for the session
        self.session.headers.update({
            "Referer": self.referer,
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

def get_config() -> List[PiholeInstance]:
    """Retrieves and validates the configuration from the environment."""
    primary_ip = os.getenv('PRIMARY_PIHOLE_IP')
    primary_token = os.getenv('PRIMARY_PIHOLE_TOKEN')
    secondary_ip = os.getenv('SECONDARY_PIHOLE_IP')
    secondary_token = os.getenv('SECONDARY_PIHOLE_TOKEN')

    if not all([primary_ip, primary_token, secondary_ip, secondary_token]):
        logging.error("Error: Ensure that PRIMARY and SECONDARY IP/Password are set in .env")
        exit(1)
    
    piholes = [
        PiholeInstance(name='Primary', ip=primary_ip, token=primary_token),
        PiholeInstance(name='Secondary', ip=secondary_ip, token=secondary_token),
    ]

    tertiary_ip = os.getenv('TERTIARY_PIHOLE_IP')
    tertiary_token = os.getenv('TERTIARY_PIHOLE_TOKEN')

    if tertiary_ip and tertiary_token:
        piholes.append(PiholeInstance(name='Tertiary', ip=tertiary_ip, token=tertiary_token))
        logging.info("Configured for 3 Pi-hole instances.")
    else:
        logging.info("Configured for 2 Pi-hole instances.")

    return piholes

def check_host_status(pihole: PiholeInstance) -> bool:
    """Checks reachability. Does not affect SID/CSRF state."""
    try:
        url = f"{pihole.base_url}/admin/"
        pihole.session.get(url, timeout=5).raise_for_status()
        pihole.is_online = True
        logging.info(f"OK: {pihole.name} is online.")
        return True
    except requests.exceptions.RequestException:
        pihole.is_online = False
        logging.warning(f"FAIL: {pihole.name} is unreachable.")
        return False

def authenticate(pihole: PiholeInstance) -> bool:
    """Gets SID and CSRF. Reuses session cookies."""
    if not pihole.is_online:
        return False

    auth_url = f"{pihole.base_url}/api/auth"
    payload = {"password": pihole.token}
    
    try:
        logging.info(f"Authenticating with {pihole.name}...")
        resp = pihole.session.post(auth_url, json=payload, timeout=10)
        resp.raise_for_status()
        
        data = resp.json().get("session", {})
        sid = data.get("sid")
        csrf = data.get("csrf")

        if not sid or not csrf:
            logging.error(f"Auth failed for {pihole.name}: SID/CSRF missing. Response: {resp.json()}")
            return False
        
        pihole.sid = sid
        pihole.csrf = csrf
        logging.info(f"New session established for {pihole.name}.")
        return True
    except Exception as e:
        logging.error(f"Auth error for {pihole.name}: {e}")
        return False

def set_dhcp_status(pihole: PiholeInstance, enable: bool):
    """Sets DHCP status using persistent SID and CSRF."""
    if not pihole.is_online:
        return

    # Authenticate only if we don't have active tokens
    if not pihole.sid or not pihole.csrf:
        if not authenticate(pihole):
            return

    action = "enabled" if enable else "disabled"
    config_url = f"{pihole.base_url}/api/config?restart=true"
    
    # Headers MUST include both sid and X-CSRF-Token
    headers = {
        "sid": pihole.sid,
        "X-CSRF-Token": pihole.csrf
    }
    payload = {"config": {"dhcp": {"active": enable}}}

    try:
        logging.info(f"Setting DHCP on {pihole.name} to {action}...")
        resp = pihole.session.patch(config_url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        
        if resp.json().get("success"):
            logging.info(f"SUCCESS: {pihole.name} DHCP is now {action}.")
        else:
            logging.warning(f"Unexpected response from {pihole.name}: {resp.json()}")

    except requests.exceptions.HTTPError as e:
        # Invalidate only on actual auth errors to prevent session seat exhaustion
        if e.response.status_code in [401, 403]:
            logging.warning(f"Session for {pihole.name} rejected (401/403). Clearing tokens.")
            pihole.sid = None
            pihole.csrf = None
            pihole.session.cookies.clear()
        else:
            logging.error(f"HTTP error for {pihole.name}: {e}")
    except Exception as e:
        logging.error(f"Request error for {pihole.name}: {e}")

def main_loop():
    logging.info("DHCP Controller started.")
    piholes = get_config()
    check_interval = int(os.getenv('CHECK_INTERVAL', '60'))

    while True:
        logging.info("--- Starting Check Cycle ---")
        for p in piholes:
            check_host_status(p)
        
        # Decision logic: first online server gets DHCP
        active_server = next((p for p in piholes if p.is_online), None)
        
        if active_server:
            logging.info(f"Active DHCP server should be: {active_server.name}")
            for p in piholes:
                set_dhcp_status(p, enable=(p == active_server))
        else:
            logging.warning("All servers offline. No DHCP action taken.")
        
        logging.info(f"--- Cycle complete. Sleeping {check_interval}s ---")
        time.sleep(check_interval)

if __name__ == "__main__":
    main_loop()