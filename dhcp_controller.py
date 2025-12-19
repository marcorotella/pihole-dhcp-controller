import os
import requests
import time
import logging
import json
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PiholeInstance:
    def __init__(self, name: str, ip: str, password: str):
        self.name = name
        # Strip whitespace and trailing slashes
        self.ip = ip.strip().rstrip('/')
        self.password = password.strip()
        self.is_online = False
        self.sid = None
        self.csrf = None
        self.session = requests.Session()
        
        # Determine base URL
        if not self.ip.startswith(('http://', 'https://')):
            self.base_url = 'http://' + self.ip
        else:
            self.base_url = self.ip
        
        # Default headers
        self.session.headers.update({
            "Referer": self.base_url + "/",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

def get_config() -> List[PiholeInstance]:
    def get_env(key):
        val = os.getenv(key)
        return val.strip() if val else None

    primary_ip = get_env('PRIMARY_PIHOLE_IP')
    primary_pw = get_env('PRIMARY_PIHOLE_TOKEN')
    secondary_ip = get_env('SECONDARY_PIHOLE_IP')
    secondary_pw = get_env('SECONDARY_PIHOLE_TOKEN')

    if not all([primary_ip, primary_pw, secondary_ip, secondary_pw]):
        logger.error("Missing mandatory PRIMARY or SECONDARY config in .env")
        exit(1)
    
    piholes = [
        PiholeInstance('Primary', primary_ip, primary_pw),
        PiholeInstance('Secondary', secondary_ip, secondary_pw),
    ]

    t_ip = get_env('TERTIARY_PIHOLE_IP')
    t_pw = get_env('TERTIARY_PIHOLE_TOKEN')
    if t_ip and t_pw:
        piholes.append(PiholeInstance('Tertiary', t_ip, t_pw))
    
    return piholes

def check_online(p: PiholeInstance):
    try:
        # Simple connectivity check
        resp = p.session.get(f"{p.base_url}/admin/", timeout=5)
        p.is_online = resp.status_code < 500
    except:
        p.is_online = False

def authenticate(p: PiholeInstance) -> bool:
    if not p.is_online: return False
    
    url = f"{p.base_url}/api/auth"
    payload = {"password": p.password}
    
    try:
        logger.info(f"[{p.name}] Attempting login...")
        resp = p.session.post(url, json=payload, timeout=10)
        
        if resp.status_code != 200:
            logger.error(f"[{p.name}] Auth failed ({resp.status_code}): {resp.text}")
            return False
            
        data = resp.json()
        session_info = data.get("session", {})
        p.sid = session_info.get("sid")
        p.csrf = session_info.get("csrf")
        
        if not p.sid:
            logger.error(f"[{p.name}] Login failed: No SID in response. Full body: {data}")
            return False
            
        # Update session state
        p.session.headers.update({
            "X-CSRF-Token": p.csrf if p.csrf else ""
        })
        logger.info(f"[{p.name}] Login successful. SID obtained.")
        return True
    except Exception as e:
        logger.error(f"[{p.name}] Auth exception: {e}")
        return False

def set_dhcp(p: PiholeInstance, enable: bool):
    if not p.is_online: return

    if not p.sid:
        if not authenticate(p): return

    state = "enabled" if enable else "disabled"
    url = f"{p.base_url}/api/config?restart=true"
    
    # We provide the SID in both the header and the JSON body as per Pi-hole v6 recommendations
    headers = {"sid": p.sid}
    payload = {
        "sid": p.sid,
        "config": {
            "dhcp": {
                "active": enable
            }
        }
    }
    
    try:
        logger.info(f"[{p.name}] Setting DHCP to {state}...")
        resp = p.session.patch(url, headers=headers, json=payload, timeout=15)
        
        if resp.status_code == 200:
            logger.info(f"[{p.name}] SUCCESS: DHCP {state}")
        else:
            logger.warning(f"[{p.name}] Failed to set DHCP (Status {resp.status_code}). Body: {resp.text}")
            if resp.status_code in [401, 403]:
                logger.info(f"[{p.name}] Resetting session due to auth error.")
                p.sid = None
                p.session.cookies.clear()
            
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
        
        master = next((p for p in piholes if p.is_online), None)
        
        if master:
            logger.info(f"Master elected: {master.name}")
            for p in piholes:
                set_dhcp(p, enable=(p == master))
        else:
            logger.warning("No Pi-hole online.")
            
        logger.info(f"Cycle complete. Waiting {interval}s...")
        time.sleep(interval)

if __name__ == "__main__":
    main()