import os
import requests
import time
import logging
import json
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup Verbose Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# To see raw HTTP headers, set to DEBUG
# logging.getLogger("urllib3").setLevel(logging.DEBUG)

class PiholeInstance:
    def __init__(self, name: str, ip: str, password: str):
        self.name = name
        self.ip = ip
        self.password = password
        self.is_online = False
        self.sid = None
        self.csrf = None
        self.session = requests.Session()
        
        # Determine base URL
        base = self.ip
        if not base.startswith(('http://', 'https://')):
            base = 'http://' + base
        self.base_url = base.rstrip('/')
        
        # Default headers for all requests
        self.session.headers.update({
            "Referer": self.base_url + "/",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

def get_config() -> List[PiholeInstance]:
    primary_ip = os.getenv('PRIMARY_PIHOLE_IP')
    primary_pw = os.getenv('PRIMARY_PIHOLE_TOKEN')
    secondary_ip = os.getenv('SECONDARY_PIHOLE_IP')
    secondary_pw = os.getenv('SECONDARY_PIHOLE_TOKEN')

    if not all([primary_ip, primary_pw, secondary_ip, secondary_pw]):
        logger.error("Missing mandatory PRIMARY or SECONDARY config in .env")
        exit(1)
    
    piholes = [
        PiholeInstance('Primary', primary_ip, primary_pw),
        PiholeInstance('Secondary', secondary_ip, secondary_pw),
    ]

    t_ip = os.getenv('TERTIARY_PIHOLE_IP')
    t_pw = os.getenv('TERTIARY_PIHOLE_TOKEN')
    if t_ip and t_pw:
        piholes.append(PiholeInstance('Tertiary', t_ip, t_pw))
    
    return piholes

def check_online(p: PiholeInstance):
    """Simple check to see if host is alive."""
    try:
        # We check the /api/info or just the admin root
        resp = p.session.get(f"{p.base_url}/admin/", timeout=5)
        p.is_online = resp.status_code < 500
    except:
        p.is_online = False

def authenticate(p: PiholeInstance) -> bool:
    """Login to get SID and CSRF."""
    if not p.is_online: return False
    
    url = f"{p.base_url}/api/auth"
    payload = {"password": p.password}
    
    try:
        logger.info(f"[{p.name}] Attempting login...")
        resp = p.session.post(url, json=payload, timeout=10)
        
        if resp.status_code != 200:
            logger.error(f"[{p.name}] Auth failed with status {resp.status_code}: {resp.text}")
            return False
            
        data = resp.json()
        session_info = data.get("session", {})
        p.sid = session_info.get("sid")
        p.csrf = session_info.get("csrf")
        
        if not p.sid or not p.csrf:
            logger.error(f"[{p.name}] Login successful but SID/CSRF missing in response.")
            return False
            
        # Explicitly set the sid cookie and X-Api-Key header
        p.session.cookies.set("sid", p.sid)
        p.session.headers.update({
            "X-Api-Key": p.sid,
            "X-CSRF-Token": p.csrf
        })
        
        logger.info(f"[{p.name}] Login successful. Session established.")
        return True
    except Exception as e:
        logger.error(f"[{p.name}] Auth exception: {e}")
        return False

def set_dhcp(p: PiholeInstance, enable: bool):
    if not p.is_online: return

    # Authenticate if session is empty
    if not p.sid:
        if not authenticate(p): return

    state = "enabled" if enable else "disabled"
    url = f"{p.base_url}/api/config?restart=true"
    payload = {"config": {"dhcp": {"active": enable}}}
    
    try:
        logger.info(f"[{p.name}] Setting DHCP to {state}...")
        resp = p.session.patch(url, json=payload, timeout=15)
        
        if resp.status_code == 200:
            logger.info(f"[{p.name}] SUCCESS: DHCP {state}")
        elif resp.status_code in [401, 403]:
            logger.warning(f"[{p.name}] Session expired (HTTP {resp.status_code}). Resetting auth tokens.")
            p.sid = None
            p.csrf = None
            p.session.cookies.clear()
        else:
            logger.error(f"[{p.name}] Failed to set DHCP. Status: {resp.status_code}, Body: {resp.text}")
            
    except Exception as e:
        logger.error(f"[{p.name}] Request error: {e}")

def main():
    logger.info("Starting Pi-hole HA DHCP Controller...")
    piholes = get_config()
    interval = int(os.getenv('CHECK_INTERVAL', '60'))

    while True:
        logger.info("--- New Cycle ---")
        for p in piholes:
            check_online(p)
            logger.info(f"[{p.name}] Status: {'ONLINE' if p.is_online else 'OFFLINE'}")
        
        # Elect Master
        master = next((p for p in piholes if p.is_online), None)
        
        if master:
            logger.info(f"Master elected: {master.name}")
            for p in piholes:
                set_dhcp(p, enable=(p == master))
        else:
            logger.warning("No Pi-hole online. Doing nothing.")
            
        logger.info(f"Cycle complete. Waiting {interval}s...")
        time.sleep(interval)

if __name__ == "__main__":
    main()
