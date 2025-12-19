import os
import requests
import time
import logging
from typing import NamedTuple, List
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env
load_dotenv()

# Configurazione del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class PiholeInstance(NamedTuple):
    name: str
    ip: str
    token: str
    is_online: bool = False

# --- Configurazione tramite Variabili d'Ambiente ---
def get_config() -> List[PiholeInstance]:
    """Recupera la configurazione dall'ambiente e la valida."""
    
    # Primario e Secondario sono obbligatori
    primary_ip = os.getenv('PRIMARY_PIHOLE_IP')
    primary_token = os.getenv('PRIMARY_PIHOLE_TOKEN')
    secondary_ip = os.getenv('SECONDARY_PIHOLE_IP')
    secondary_token = os.getenv('SECONDARY_PIHOLE_TOKEN')

    if not all([primary_ip, primary_token, secondary_ip, secondary_token]):
        logging.error("Errore: Assicurati che IP e TOKEN siano impostati almeno per i server PRIMARY e SECONDARY.")
        exit(1)
    
    piholes = [
        PiholeInstance(name='Primary', ip=primary_ip, token=primary_token),
        PiholeInstance(name='Secondary', ip=secondary_ip, token=secondary_token),
    ]

    # Terziario è opzionale
    tertiary_ip = os.getenv('TERTIARY_PIHOLE_IP')
    tertiary_token = os.getenv('TERTIARY_PIHOLE_TOKEN')

    if tertiary_ip and tertiary_token:
        piholes.append(PiholeInstance(name='Tertiary', ip=tertiary_ip, token=tertiary_token))
        logging.info("Rilevata configurazione per 3 server (Primario, Secondario, Terziario).")
    else:
        logging.info("Rilevata configurazione per 2 server (Primario, Secondario). Il terziario viene ignorato.")

    return piholes

CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', '60'))

def check_host_status(pihole: PiholeInstance) -> bool:
    """Controlla se un'istanza Pi-hole è raggiungibile."""
    try:
        response = requests.get(f"http://{pihole.ip}/admin/", timeout=5)
        response.raise_for_status()
        logging.info(f"OK: {pihole.name} Pi-hole ({pihole.ip}) è online.")
        return True
    except (requests.exceptions.RequestException) as e:
        logging.warning(f"FAIL: {pihole.name} Pi-hole ({pihole.ip}) non è raggiungibile. Errore: {e}")
        return False

def set_dhcp_status(pihole: PiholeInstance, enable: bool):
    """Abilita o disabilita il DHCP su una specifica istanza Pi-hole."""
    if not pihole.is_online:
        logging.info(f"SKIP: {pihole.name} è offline, impossibile modificare lo stato del DHCP.")
        return

    action = "enable" if enable else "disable"
    url = f"http://{pihole.ip}/admin/api.php"
    
    try:
        params = {"auth": pihole.token, action: "dhcp"}
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        if data.get("status") == f"dhcp_{action}d":
            logging.info(f"SUCCESS: DHCP {action}d su {pihole.name} ({pihole.ip}).")
        else:
            logging.info(f"INFO: Lo stato DHCP su {pihole.name} era già {action}d. Nessuna modifica.")
            
    except (requests.exceptions.RequestException, ValueError) as e:
        logging.error(f"ERROR: Impossibile modificare lo stato DHCP su {pihole.name}. Errore: {e}")

def main_loop():
    """Ciclo principale che orchestra lo stato DHCP dei server."""
    logging.info("Servizio di controllo DHCP avviato.")
    
    piholes = get_config()

    while True:
        logging.info("--- Inizio nuovo ciclo di controllo ---")
        
        # 1. Controlla lo stato di tutti i Pi-hole
        online_piholes = [p._replace(is_online=check_host_status(p)) for p in piholes]
        
        # 2. Determina quale server deve essere il master DHCP (il primo online nella lista)
        active_dhcp_server = next((p for p in online_piholes if p.is_online), None)
        
        if active_dhcp_server:
            logging.info(f"DECISIONE: {active_dhcp_server.name} ({active_dhcp_server.ip}) sarà il server DHCP attivo.")
        else:
            logging.warning("ATTENZIONE: Nessun Pi-hole è online. Impossibile attivare un server DHCP.")

        # 3. Applica la decisione: abilita sul master, disabilita su tutti gli altri
        for p in online_piholes:
            if p == active_dhcp_server:
                set_dhcp_status(p, enable=True) # Abilita il master
            else:
                set_dhcp_status(p, enable=False) # Disabilita gli altri
        
        logging.info(f"--- Ciclo di controllo completato. Prossimo controllo tra {CHECK_INTERVAL} secondi. ---")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main_loop()
