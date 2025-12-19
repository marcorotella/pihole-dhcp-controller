# Pi-hole DHCP Controller

Questo progetto implementa un sistema di failover e failback centralizzato per la gestione del server DHCP su più istanze Pi-hole (due o tre). Il controllore monitora lo stato di salute di tutti i Pi-hole configurati e assicura che il server DHCP sia attivo solo sull'istanza di più alta priorità attualmente online, prevenendo conflitti di DHCP e garantendo la continuità del servizio.

## Funzionalità

*   **Controllo Centralizzato:** Un singolo servizio gestisce lo stato DHCP di tutte le tue istanze Pi-hole.
*   **Logica di Failover Gerarchica:** Definisce una priorità tra i server (Primario > Secondario > Terziario). Il DHCP sarà attivo solo sul server di più alta priorità che è raggiungibile.
*   **Failback Automatico:** Se un server di priorità più alta torna online, riprende automaticamente il ruolo di server DHCP, disabilitando il DHCP sugli altri server.
*   **Supporto Flessibile (2 o 3 server):** Lo script rileva automaticamente se stai utilizzando due o tre server Pi-hole in base alla configurazione.
*   **Configurazione Semplice:** Tutte le impostazioni sono gestite tramite un file `.env`.
*   **Deploy con Docker Compose:** Facile da installare e gestire tramite Docker Compose su una VM dedicata.

## Prerequisiti

*   **Docker e Docker Compose:** Installati sulla VM che ospiterà il servizio di controllo.
*   **Istanze Pi-hole Funzionanti:** Tutti i Pi-hole devono essere configurati e accessibili via rete dalla VM del controllore.
*   **API Token di Pi-hole:** Per ogni istanza Pi-hole che vuoi gestire, dovrai generare un token API dall'interfaccia di amministrazione (Settings > API / Web interface).

## Installazione e Configurazione

1.  **Clona il Repository:**
    ```bash
    git clone https://github.com/marcorotella/pihole-dhcp-controller.git
    cd pihole-dhcp-controller
    ```

2.  **Crea il file di configurazione `.env`:**
    *   Copia il file `.env.example` in `.env`:
        ```bash
        cp .env.example .env
        ```
    *   Apri il file `.env` con un editor di testo e compila le variabili:
        ```ini
        # --- Configurazione del Controllore DHCP per Pi-hole ---

        # Intervallo di controllo in secondi
        CHECK_INTERVAL=60

        # --- Pi-hole Primario (Priorità 1 - Obbligatorio) ---
        PRIMARY_PIHOLE_IP=IL_TUO_IP_PRIMARIO
        PRIMARY_PIHOLE_TOKEN=IL_TUO_TOKEN_API_PRIMARIO

        # --- Pi-hole Secondario (Priorità 2 - Obbligatorio) ---
        SECONDARY_PIHOLE_IP=IL_TUO_IP_SECONDARIO
        SECONDARY_PIHOLE_TOKEN=IL_TUO_TOKEN_API_SECONDARIO

        # --- Pi-hole Terziario (Priorità 3 - Opzionale) ---
        # Lascia queste due variabili vuote o commentale per un setup a 2 server.
        # Se compilate, lo script passerà automaticamente a una gestione a 3 server.
        TERTIARY_PIHOLE_IP=
        TERTIARY_PIHOLE_TOKEN=
        ```
    *   **Importante:** Assicurati di inserire gli IP corretti e i token API generati per ogni Pi-hole.

3.  **Avvia il Servizio con Docker Compose:**
    *   Dalla stessa directory dove si trova `docker-compose.yml` ed `.env`, esegui:
        ```bash
        docker-compose up -d --build
        ```
    *   Questo comando costruirà l'immagine Docker (se non già presente o se ci sono modifiche) e avvierà il servizio in background.

## Logica di Funzionamento

Il `dhcp_controller` esegue un ciclo di controllo ogni `CHECK_INTERVAL` secondi:

1.  **Verifica lo stato di tutti i Pi-hole:** Controlla la raggiungibilità di Primario, Secondario e Terziario (se configurato).
2.  **Determina il Server DHCP Attivo:**
    *   Se il **Primario** è online, sarà lui il server DHCP attivo.
    *   Altrimenti, se il **Secondario** è online, sarà lui il server DHCP attivo.
    *   Altrimenti, se il **Terziario** è online, sarà lui il server DHCP attivo.
    *   Se nessun Pi-hole è online, nessun server DHCP sarà attivato.
3.  **Applica le Modifiche:**
    *   Abilita il DHCP sul server scelto come "attivo".
    *   Disabilita il DHCP su tutti gli altri server online.

Questa logica garantisce che il servizio DHCP sia sempre gestito dal server di più alta priorità disponibile e permette un ripristino automatico del servizio sul server primario non appena torna online.

## Monitoraggio

Per monitorare il funzionamento del controllore e visualizzare i log in tempo reale:

```bash
docker-compose logs -f
```
