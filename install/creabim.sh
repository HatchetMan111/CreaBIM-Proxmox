#!/usr/bin/env bash
# =============================================================================
#  🏛️  CreaBIM Server – One-Click-Installer (Proxmox VE)
#  https://github.com/HatchetMan111/CreaBIM-Proxmox
#
#  Erstellt einen unprivilegierten LXC-Container und installiert darin den
#  CreaBIM-Server: eine lokale Weboberfläche (React/Vite + FastAPI) um die
#  headless »creabim-cli« von CreaBIM (https://github.com/chopinregis/CreaBIM).
#
#  Architektur im Container:
#    - creabim-cli aus dem offiziellen Release (SHA-256-geprüft, kein Rust-Build)
#    - FastAPI-Backend (Python) servt /api/* + die gebaute SPA
#    - systemd-Service creabim-server.service (Restart=always, Boot-Start)
#    - optional (--gui): Xvfb + CreaBIM-GUI + x11vnc + noVNC auf Port+1
#
#  Installation (auf dem Proxmox-Host als root):
#    bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/CreaBIM-Proxmox/main/install/creabim.sh)"
#
#  Mit Optionen (direkt hinter dem schließenden Anführungszeichen):
#    ... " --id 210 --memory 4096 --port 8030
#
#  Update / Deinstall / Status / Debug:
#    ... " --update        |  ... " --uninstall  |  ... " --status  |  ... " --debug
# =============================================================================

# shellcheck disable=SC1111  # deutsche Anführungszeichen („…“) sind Absicht
set -Eeuo pipefail

# ── Defaults ────────────────────────────────────────────────────────────────
INSTALLER_VERSION="1.0.0"
APP_NAME="creabim"
APP_PRETTY="CreaBIM Server"
UPSTREAM_OWNER="HatchetMan111"
UPSTREAM_REPO="CreaBIM-Proxmox"
UPSTREAM_BRANCH="main"      # Update-Quelle des Server-Codes
UPSTREAM_TARBALL_URL="https://codeload.github.com/${UPSTREAM_OWNER}/${UPSTREAM_REPO}/tar.gz/refs/heads/${UPSTREAM_BRANCH}"

# Die App selbst kommt als offizielles Release von chopinregis/CreaBIM.
# "latest" holt das neueste Release; zum Fixen eine Version wie "v1.1.1" angeben.
CREABIM_OWNER="chopinregis"
CREABIM_REPO="CreaBIM"
CREABIM_VERSION="latest"
CREABIM_TARBALL_URL=""      # wird zur Laufzeit aus dem Release ermittelt
CREABIM_SHA256=""           # Checksummen-Zeile aus SHA256SUMS.txt

NODE_MAJOR=22               # nur nötig, wenn kein vorgebautes Frontend dabei liegt
CT_ID=""                    # leer = automatisch nächste freie ID ab ID_SCAN_START
ID_SCAN_START=200
CT_HOSTNAME="creabim"
CT_STORAGE="local-lvm"
CT_ROOTFS=6                 # GB – Debian + Python + creabim-cli + SPA
CT_CORES=2
CT_MEMORY=2048              # MB
CT_SWAP=1024                # MB Puffer für PDF-Exporte
CT_BRIDGE="vmbr0"
CT_IP="dhcp"
CT_GATEWAY=""               # nur bei statischer IP nötig, z. B. 192.168.1.1
CT_PASSWORD=""              # leer = automatisch generieren
CT_SSHKEY=""                # Pfad ODER URL zu einer Public-Key-Datei (optional)
SSH_KEY_FILE=""             # aufgelöste Key-Datei für pct create
PORT=8030                   # Web-UI-Port im Container
GUI_PORT=8031               # noVNC-Port (nur mit --gui)
INSTALL_GUI=false           # CreaBIM-GUI zusätzlich über noVNC bereitstellen
GUI_PASSWORD=""             # leer = automatisch generieren
UNINSTALL=false
UPDATE=false
STATUS_CHECK=false
FORCE_RECREATE=false
ASSUME_YES=false
TMP_DIR=""
LOG_FILE="/tmp/${APP_NAME}-installer-$(date +%Y%m%d-%H%M%S).log"
# Der fertige Einzeiler für Hinweise/Fehlerausgaben – exakt kopierbar (Optionen
# hinter dem schließenden Anführungszeichen; der Installer erkennt sie via $0-Fallback)
# shellcheck disable=SC2016  # Absicht: Literal, das zum Ausgeben gedacht ist
ONE_LINER='bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/CreaBIM-Proxmox/main/install/creabim.sh)"'

# ── Farben & Logging ───────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'; BOLD='\033[1m'

info()  { echo -e "${BLUE}ℹ${NC}  $1"; }
ok()    { echo -e "${GREEN}✔${NC}  $1"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $1"; }
err()   { echo -e "${RED}✘${NC}  $1" >&2; }
die()   { err "$1"; exit 1; }
header(){ echo -e "\n${CYAN}${BOLD}━━━ $1 ━━━${NC}"; }

# ── Vollständiges Log mitschneiden (Debugging-Anforderung) ─────────────────
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
exec > >(tee "$LOG_FILE") 2>&1

# ── Cleanup & Fehlerkette ──────────────────────────────────────────────────
cleanup() {
    # if statt [[ ]] && – sonst gibt cleanup() bei leerem TMP_DIR Exit-Code 1
    # zurück und überschreibt den eigentlichen Exit-Status des Scripts.
    if [[ -n "${TMP_DIR:-}" && -d "$TMP_DIR" ]]; then
        rm -rf "$TMP_DIR"
    fi
}
trap cleanup EXIT

# Gibt bei Fehlern die KOMPLETTE Fehlerkette aus: Zeile, Befehl, Exit-Code,
# letzte Logzeilen sowie Container-Logs (Setup + creabim-server), falls schon
# ein Container existiert.
on_error() {
    local ec=$1 line=$2 cmd=$3
    err "Installationsfehler – Exit-Code ${ec} in Zeile ${line}"
    err "Fehlgeschlagener Befehl: ${cmd}"
    if [[ -f "$LOG_FILE" ]]; then
        info "Letzte Logzeilen (${LOG_FILE}):"
        tail -n 20 "$LOG_FILE" | sed 's/^/    /' || true
    fi
    if [[ -n "${CT_ID:-}" ]] && pct status "$CT_ID" &>/dev/null; then
        info "Container-Logs (Setup + creabim-server):"
        pct exec "$CT_ID" -- sh -c '
            tail -n 40 /var/log/creabim-setup.log 2>/dev/null
            echo "--- journalctl -u creabim-server ---"
            journalctl -u creabim-server --no-pager 2>/dev/null | tail -n 25
            echo "--- journalctl -u creabim-gui ---"
            journalctl -u creabim-gui --no-pager 2>/dev/null | tail -n 15
        ' 2>/dev/null | sed 's/^/    /' || true
        info "Container $CT_ID wurde NICHT gelöscht – Inspektion: pct enter $CT_ID"
        info "Aufräumen: pct stop $CT_ID && pct destroy $CT_ID --purge"
    fi
    info "Vollständiges Log: $LOG_FILE"
    info "Neu ausführen mit vollem bash -x-Trace (exakter Befehl):"
    echo "    ${ONE_LINER} --debug"
    exit "$ec"
}
trap 'on_error $? $LINENO "$BASH_COMMAND"' ERR

# ── Debug-Modus (voller bash -x-Trace) ─────────────────────────────────────
# (Vor parse_args, damit --debug selbst noch mitgetraced wird.)
if [[ "${1:-}" == "--debug" || "$0" == "--debug" ]]; then
    set -x
fi

# ── Hilfsfunktionen ────────────────────────────────────────────────────────
ct_exists() {
    # NAME ist Spalte 2 (pct list: VMID(1) NAME(2) STATUS(3) MEM(4) BOOTDISK(5) PID(6))
    # – NICHT $NF! (Frühere Installer-Vorlagen nutzten $NF; das matcht die PID.)
    if pct list 2>/dev/null | awk 'NR>1 {print $2}' | grep -qx "${1:-}"; then
        return 0
    fi
    return 1
}

find_free_id() {
    local id="$ID_SCAN_START"
    while pct list 2>/dev/null | awk '{print $1}' | grep -qx "$id"; do
        id=$((id + 1))
    done
    echo "$id"
}

find_ct_id_by_hostname() {
    # NAME ist Spalte 2 – NICHT $NF (das wäre die PID).
    pct list 2>/dev/null | awk -v h="$CT_HOSTNAME" '$2==h {print $1; exit}'
}

get_ct_ip() {
    # Grube (pipefail): bei pct-exec-Fehlschlag stirbt die Substitution –
    # deshalb || true INNERHALB von $(). Bei statischer IP direkt nutzen.
    local ct_id="$1"
    if [[ "$CT_IP" != "dhcp" ]]; then
        echo "${CT_IP%%/*}"
        return 0
    fi
    pct exec "$ct_id" -- hostname -I 2>/dev/null | awk '{print $1}' || true
    return 0
}

wait_for_ct_network() {
    # Nach pct create --start nicht blind sleep 3 (DHCP/DNS-Race) – aktiv pollen.
    local id="$1" tries=0 ip=""
    info "Warte auf Netzwerk im Container (DHCP) ..."
    while true; do
        ip=$(pct exec "$id" -- hostname -I 2>/dev/null | awk '{print $1}' || true)
        if [[ -n "$ip" ]]; then
            ok "Container-IP: $ip"
            return 0
        fi
        tries=$((tries + 1))
        if [[ $tries -ge 60 ]]; then
            err "Container hat nach 60 s keine IP bekommen."
            info "Prüfe: pct exec $id -- ip a   und DHCP am Bridge-Interface ($CT_BRIDGE)"
            return 1
        fi
        sleep 1
    done
}

verify_ct_dns() {
    # IP allein reicht nicht – Release-Download und GitHub brauchen Namensauflösung.
    # Live-Fall (2026-11-10): DNS ist FLAKY – ein einzelner getent-Erfolg reichte,
    # Stunden später war wieder alles tot. Deshalb: 3 Erfolge in Folge verlangen.
    local id="$1" ok_count=0 tries=0
    info "Prüfe DNS im Container (3x hintereinander) ..."
    while true; do
        if pct exec "$id" -- getent hosts github.com >/dev/null 2>&1; then
            ok_count=$((ok_count + 1))
            if [[ $ok_count -ge 3 ]]; then
                ok "DNS im Container funktioniert (3x bestätigt)"
                return 0
            fi
        else
            ok_count=0
        fi
        tries=$((tries + 1))
        if [[ $tries -ge 10 ]]; then
            break
        fi
        sleep 2
    done
    # Fallback: DNS des Hosts (falls nicht loopback) + öffentliche Resolver eintragen
    local host_ns ns_list
    host_ns=$(grep -h '^nameserver' /etc/resolv.conf 2>/dev/null | awk '{print $2}' | grep -v '^127\.' | head -1 || true)
    ns_list="1.1.1.1 8.8.8.8 9.9.9.9"
    if [[ -n "$host_ns" ]]; then
        ns_list="$host_ns $ns_list"
    fi
    warn "DNS im Container defekt – schreibe Fallback-Nameserver ($ns_list) nach /etc/resolv.conf"
    pct exec "$id" -- sh -c "printf 'nameserver %s\n' $ns_list > /etc/resolv.conf"
    # Dauerhaft: dhclient-Hook (chattr +i funktioniert in unprivilegierten LXCs nicht)
    pct exec "$id" -- bash -c 'mkdir -p /etc/dhcp/dhclient-enter-hooks.d && printf "make_resolv_conf() { :; }\n" > /etc/dhcp/dhclient-enter-hooks.d/no-dns'
    if pct exec "$id" -- getent hosts github.com >/dev/null 2>&1; then
        ok "DNS-Fallback aktiv und gegen DHCP-Überschreiben geschützt"
        return 0
    fi
    die "DNS im Container weiterhin ohne Funktion (auch mit Fallback).
  Prüfe: pct exec $id -- cat /etc/resolv.conf && pct exec $id -- ping -c2 1.1.1.1
  Firewall/Router: ausgehende DNS-Anfragen (Port 53) am Bridge-Netz erlauben."
}

ensure_ct_running() {
    # Update-/Verwaltungs-Pfade müssen einen GESTOPPTEN CT selbst starten –
    # pct exec auf gestopptem CT scheitert kryptisch (Exit 255).
    local ct_id="$1"
    local state
    state=$(pct status "$ct_id" 2>/dev/null || echo "unknown")
    if [[ "$state" == *"running"* ]]; then
        return 0
    fi
    warn "Container $ct_id läuft nicht (Status: ${state}) – starte ihn ..."
    if ! pct start "$ct_id" 2>&1 | tail -2; then
        die "Container $ct_id konnte nicht gestartet werden.\n  Manuell prüfen: pct start $ct_id && pct status $ct_id"
    fi
    info "Warte auf Netzwerk des Containers ..."
    local i ip=""
    for i in $(seq 1 60); do
        ip=$(pct exec "$ct_id" -- hostname -I 2>/dev/null | tr -d ' \n' || true)
        if [[ -n "$ip" ]]; then
            ok "Container läuft (IP: ${ip%% *})"
            return 0
        fi
        sleep 1
    done
    die "Container $ct_id hat nach 60 s keine IP (Bridge/Netz prüfen: pct exec $ct_id -- ip a)"
}

# ── Release-Auflösung (offizielles CreaBIM-Release + SHA-256) ──────────────
resolve_release() {
    # Ermittelt Tarball-URL und SHA-256 des Linux-x64-Releases. Die Assets
    # heißen "CreaBIM-<version>-<datum>-linux-x64.tar.gz" – das Datum steckt
    # im Namen, deshalb wird das Asset über die API gesucht und nicht geraten.
    if [[ -n "$CREABIM_TARBALL_URL" ]]; then
        info "Release-URL ist vorgegeben: $CREABIM_TARBALL_URL"
        return 0
    fi
    local api="https://api.github.com/repos/${CREABIM_OWNER}/${CREABIM_REPO}/releases"
    if [[ "$CREABIM_VERSION" == "latest" ]]; then
        api="${api}/latest"
    else
        api="${api}/tags/${CREABIM_VERSION}"
    fi

    header "📦 CreaBIM-Release auflösen"
    info "Quelle: $api"
    local json
    json=$(curl -fsSL --retry 3 --retry-delay 2 \
           -H 'Accept: application/vnd.github+json' "$api") \
        || die "GitHub-API nicht erreichbar ($api).
  Offline-Installation: CREABIM_TARBALL_URL=<direkte Asset-URL> ${ONE_LINER}"
    local urls
    urls=$(printf '%s\n' "$json" | grep -o '"browser_download_url": *"[^"]*"' \
           | sed 's/.*": *"//; s/"$//' || true)

    CREABIM_TARBALL_URL=$(printf '%s\n' "$urls" | grep -E -- '-linux-x64\.tar\.gz$' | head -1 || true)
    local sums_url
    sums_url=$(printf '%s\n' "$urls" | grep -E 'SHA256SUMS\.txt$' | head -1 || true)

    if [[ -z "$CREABIM_TARBALL_URL" ]]; then
        die "Im Release ${CREABIM_VERSION} wurde kein Linux-x64-tar.gz gefunden.
  Verfügbare Assets:
$(printf '%s\n' "$urls" | sed 's/^/    /')"
    fi
    info "Tarball: $CREABIM_TARBALL_URL"

    # Checksummen besorgen und die Zeile für unseren Tarball herausziehen.
    local tarball_name
    tarball_name=$(basename "$CREABIM_TARBALL_URL")
    if [[ -n "$sums_url" ]]; then
        local sums_file="$TMP_DIR/SHA256SUMS.txt"
        if curl -fsSL --retry 3 "$sums_url" -o "$sums_file"; then
            CREABIM_SHA256=$(awk -v f="$tarball_name" '$2 == f {print $1}' "$sums_file" | head -1 || true)
            [[ -n "$CREABIM_SHA256" ]] \
                || warn "SHA256SUMS.txt enthält keinen Eintrag für $tarball_name – Prüfung entfällt."
        else
            warn "SHA256SUMS.txt konnte nicht geladen werden – Prüfung entfällt."
        fi
    else
        warn "Release enthält keine SHA256SUMS.txt – Prüfung entfällt."
    fi
    if [[ -n "$CREABIM_SHA256" ]]; then
        ok "SHA-256 erwartet: $CREABIM_SHA256"
    fi
    return 0
}

# ── Templatewahl ───────────────────────────────────────────────────────────
template_for_debian() {
    local major="$1"
    pveam list local 2>/dev/null \
        | grep -E "debian-${major}[^ ]*standard" \
        | sort -V | tail -1 | awk '{print $1}'
}

ensure_template() {
    # Liefert den Vol-ID eines Debian-<major>-Templates, lädt es bei Bedarf.
    local major="$1" tpl=""
    tpl=$(template_for_debian "$major")
    if [[ -z "$tpl" ]]; then
        info "Kein Debian-${major}-Template lokal – lade es herunter ..."
        pveam update >/dev/null 2>&1 || true
        local avail
        avail=$(pveam available 2>/dev/null \
                | grep -E "debian-${major}[^ ]*standard" | tail -1 | awk '{print $2}' || true)
        if [[ -z "$avail" ]]; then
            return 1
        fi
        pveam download local "$avail" >/dev/null 2>&1 || return 1
        tpl=$(template_for_debian "$major")
    fi
    if [[ -z "$tpl" ]]; then
        return 1
    fi
    echo "$tpl"
}

# ── Argumente parsen ───────────────────────────────────────────────────────
parse_args() {
    # Grube (bash -c): `bash -c "$(wget -qLO - URL)" --id 5` belegt das ERSTE
    # Argument nach dem Script-String mit $0, nicht $1 – die Option würde
    # still geschluckt. Fallback: startet $0 mit "-", ist es eine Option.
    local args=("$@")
    if [[ "$0" == -* ]]; then
        args=("$0" "$@")
    fi
    local i=0
    while [[ $i -lt ${#args[@]} ]]; do
        case "${args[$i]}" in
            --id)            CT_ID="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --hostname)      CT_HOSTNAME="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --storage)       CT_STORAGE="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --rootfs)        CT_ROOTFS="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --cores)         CT_CORES="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --memory)        CT_MEMORY="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --swap)          CT_SWAP="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --bridge)        CT_BRIDGE="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --ip)            CT_IP="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --gateway)       CT_GATEWAY="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --password)      CT_PASSWORD="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --sshkey)        CT_SSHKEY="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --port)          PORT="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --gui-port)      GUI_PORT="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --gui-password)  GUI_PASSWORD="${args[$((i+1))]:-}"; i=$((i+2)) ;;
            --gui)           INSTALL_GUI=true; i=$((i+1)) ;;
            --force)         FORCE_RECREATE=true; i=$((i+1)) ;;
            --yes|-y)        ASSUME_YES=true; i=$((i+1)) ;;
            --update)        UPDATE=true; i=$((i+1)) ;;
            --uninstall)     UNINSTALL=true; i=$((i+1)) ;;
            --status)        STATUS_CHECK=true; i=$((i+1)) ;;
            --debug)         set -x; i=$((i+1)) ;;
            --help|-h)       print_help; exit 0 ;;
            *) die "Unbekannte Option: ${args[$i]}  (–help zeigt alle Optionen)" ;;
        esac
    done
    # Ports hart validieren – sie landen direkt im systemd-Service.
    local p
    for p in "$PORT" "$GUI_PORT"; do
        if ! [[ "$p" =~ ^[0-9]+$ ]] || [[ "$p" -lt 1 || "$p" -gt 65535 ]]; then
            die "Ungültiger Port: '$p' (1–65535 erwartet, z. B. --port 8030)"
        fi
    done
    if [[ "$PORT" == "$GUI_PORT" ]]; then
        die "Web-UI-Port und noVNC-Port dürfen nicht gleich sein ($PORT)."
    fi
    # GUI braucht mehr Luft – Defaults anheben, wenn der Nutzer nichts gesetzt hat.
    if $INSTALL_GUI; then
        if [[ "$CT_MEMORY" == "2048" ]]; then CT_MEMORY=4096; fi
        if [[ "$CT_ROOTFS" == "6" ]]; then CT_ROOTFS=10; fi
        if [[ "$CT_SWAP" == "1024" ]]; then CT_SWAP=2048; fi
    fi
}

print_help() {
    cat <<'EOF'
🏛️  CreaBIM Server – Proxmox-Installer

Lokale BIM-Web-App: Projekte verwalten, Grundrisse/Schnitte/Pläne rendern und
als PDF, IFC, XLSX, CSV, glTF oder FreeCAD exportieren – alles offline im LXC.

Installation:   bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/CreaBIM-Proxmox/main/install/creabim.sh)"

Optionen (hinter dem schließenden Anführungszeichen anhängen, z. B. ... " --id 210):
  --id ID          Container-ID (Default: nächste freie ab 200)
  --hostname NAME  Container-Hostname (Default: creabim)
  --storage NAME   Storage für rootfs (Default: local-lvm)
  --rootfs GB      Disk-Größe (Default: 6, mit --gui 10)
  --cores N        vCPUs (Default: 2)
  --memory MB      RAM (Default: 2048, mit --gui 4096)
  --swap MB        Swap (Default: 1024, mit --gui 2048)
  --bridge BR      Netzwerk-Bridge (Default: vmbr0)
  --ip CIDR        Statt DHCP, z. B. 192.168.1.50/24 (+ --gateway 192.168.1.1)
  --gateway GW     Gateway für statische IP
  --password PW    Root-Passwort (Default: automatisch generiert)
  --sshkey PFAD    Public-Key-Datei oder URL – ssh-key-Login als root im CT
  --port PORT      Web-UI-Port im Container (Default: 8030)
  --gui            Zusätzlich die CreaBIM-GUI über noVNC (Port 8031, --gui-port)
  --gui-password PW  VNC-Passwort für noVNC (Default: automatisch generiert)
  --force          Vorhandenen Container mit gleichem Hostname löschen und neu anlegen
  --yes / -y       Rückfragen überspringen
  --update         Server im bestehenden Container aktualisieren (neues Release + Code)
  --uninstall      Container stoppen und löschen
  --status         Status anzeigen
  --debug          Vollständiges bash -x-Trace

  Modus:  Install (Default) / --update / --uninstall / --status / --debug
EOF
}

# ── In-Container-Setup-Script (idempotent) ─────────────────────────────────
# ACHTUNG: QUOTETER Heredoc ('INNEREOF') – nichts wird vom HOST-Script expandiert.
# Alle Werte kommen als Umgebungsvariablen via `pct exec -- env …` in den Container.
write_inner_script() {
    cat > "$TMP_DIR/setup-inner.sh" <<'INNEREOF'
#!/usr/bin/env bash
# =============================================================================
# CreaBIM-Server In-Container-Setup (idempotent – safe für Update & Re-Run)
# Variablen via env: PORT, GUI_PORT, INSTALL_GUI, CREABIM_TARBALL_URL,
#                    CREABIM_SHA256, CREABIM_VERSION, HOST_DNS,
#                    UPSTREAM_TARBALL_URL, NODE_MAJOR, APP_USER, GUI_PASSWORD
# =============================================================================
set -Eeuo pipefail
trap 'echo "✘ Setup-Fehler: exit $? in Zeile $LINENO: $BASH_COMMAND" >&2' ERR
export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C

err(){ echo "✘ $1" >&2; }
die(){ err "$1"; exit 1; }

: "${PORT:?PORT fehlt (env)}"
: "${GUI_PORT:?GUI_PORT fehlt (env)}"
: "${INSTALL_GUI:?INSTALL_GUI fehlt (env)}"
: "${CREABIM_TARBALL_URL:?CREABIM_TARBALL_URL fehlt (env)}"
: "${CREABIM_VERSION:?CREABIM_VERSION fehlt (env)}"
: "${HOST_DNS:?HOST_DNS fehlt (env)}"
: "${UPSTREAM_TARBALL_URL:?UPSTREAM_TARBALL_URL fehlt (env)}"
: "${NODE_MAJOR:?NODE_MAJOR fehlt (env)}"
APP_USER="${APP_USER:-creabim}"
APP_ROOT=/opt/creabim

echo ">>> Grundpakete installieren ..."
apt-get update -qq
apt-get install -y -qq ca-certificates curl wget xz-utils \
    python3 python3-venv python3-pip >/dev/null

echo ">>> DNS festschreiben (DHCP-DNS des Netzes ist unzuverlässig) ..."
mkdir -p /etc/dhcp/dhclient-enter-hooks.d
printf '# CreaBIM: resolv.conf nicht von DHCP überschreiben lassen\nmake_resolv_conf() { :; }\n' \
    > /etc/dhcp/dhclient-enter-hooks.d/no-dns
printf 'domain home.arpa\nsearch home.arpa\nnameserver %s\nnameserver 1.1.1.1\nnameserver 8.8.8.8\nnameserver 9.9.9.9\n' \
    "${HOST_DNS}" > /etc/resolv.conf

echo ">>> CreaBIM ${CREABIM_VERSION} herunterladen ..."
mkdir -p "${APP_ROOT}/dist"
curl -fSL --retry 3 "${CREABIM_TARBALL_URL}" -o /tmp/creabim.tar.gz
if [ -n "${CREABIM_SHA256:-}" ]; then
    echo ">>> SHA-256 prüfen (${CREABIM_SHA256}) ..."
    echo "${CREABIM_SHA256}  /tmp/creabim.tar.gz" | sha256sum -c - \
        || die "SHA-256 stimmt nicht mit SHA256SUMS.txt überein – Abbruch."
else
    echo "⚠  Keine SHA-256-Prüfsumme verfügbar – überspringe die Prüfung."
fi
rm -rf /tmp/creabim-dist && mkdir -p /tmp/creabim-dist
tar -xzf /tmp/creabim.tar.gz -C /tmp/creabim-dist --strip-components=1
[ -x /tmp/creabim-dist/creabim-cli ] \
    || die "creabim-cli fehlt im Release-Tarball. Inhalt: $(ls /tmp/creabim-dist | tr '\n' ' ')"

echo ">>> creabim-cli installieren ..."
mkdir -p "${APP_ROOT}/bin"
install -m 0755 /tmp/creabim-dist/creabim-cli "${APP_ROOT}/bin/creabim-cli"
if [ "${INSTALL_GUI}" = "true" ]; then
    [ -f /tmp/creabim-dist/creabim ] || die "creabim (GUI) fehlt im Release-Tarball."
    install -m 0755 /tmp/creabim-dist/creabim "${APP_ROOT}/bin/creabim"
fi
"${APP_ROOT}/bin/creabim-cli" stats 2>/dev/null | head -1 || true

echo ">>> Server-Code aus dem Repo laden (${UPSTREAM_TARBALL_URL}) ..."
curl -fSL --retry 3 "${UPSTREAM_TARBALL_URL}" -o /tmp/creabim-src.tar.gz
rm -rf /tmp/creabim-src && mkdir -p /tmp/creabim-src
tar -xzf /tmp/creabim-src.tar.gz -C /tmp/creabim-src --strip-components=1
if [ ! -f /tmp/creabim-src/app/backend/main.py ]; then
    die "Unerwartete Repo-Struktur: app/backend/main.py fehlt.
  Erwartet: app/backend/ + app/frontend/ (dieses Repo). Tarball-Inhalt:
  $(ls /tmp/creabim-src | head -10 | tr '\n' ' ')"
fi
rm -rf "${APP_ROOT}/src" && mkdir -p "${APP_ROOT}/src/backend"
cp -a /tmp/creabim-src/app/backend/. "${APP_ROOT}/src/backend/"

echo ">>> Virtuelles Environment + Python-Abhängigkeiten ..."
python3 -m venv "${APP_ROOT}/.venv"
"${APP_ROOT}/.venv/bin/pip" install --quiet --upgrade pip
"${APP_ROOT}/.venv/bin/pip" install --quiet -r "${APP_ROOT}/src/backend/requirements.txt"

# ── Frontend ───────────────────────────────────────────────────────────────
if [ -f "${APP_ROOT}/src/backend/static/index.html" ]; then
    echo ">>> Vorgebautes Frontend vorhanden – übernehmen."
else
    echo ">>> Kein fertiges Frontend im Repo – baue es mit Node.js ${NODE_MAJOR} ..."
    apt-get install -y -qq nodejs >/dev/null 2>&1 || {
        curl -fsSL --retry 3 "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" -o /tmp/nodesource-setup.sh
        bash /tmp/nodesource-setup.sh >/dev/null
        apt-get install -y -qq nodejs >/dev/null
    }
    hash -r
    cp -a /tmp/creabim-src/app/frontend "${APP_ROOT}/src/frontend"
    cd "${APP_ROOT}/src/frontend"
    npm install --no-audit --no-fund --loglevel=error
    npm run build
    if [ ! -f "${APP_ROOT}/src/backend/static/index.html" ]; then
        die "Frontend-Build fehlgeschlagen: static/index.html fehlt (npm-Ausgabe oben)."
    fi
fi

# ── Benutzer & Rechte ──────────────────────────────────────────────────────
id -u "${APP_USER}" &>/dev/null \
    || useradd --system --no-create-home --shell /usr/sbin/nologin "${APP_USER}"
mkdir -p "${APP_ROOT}/data"
chown -R "${APP_USER}:${APP_USER}" "${APP_ROOT}"

# ── systemd: Server ────────────────────────────────────────────────────────
echo ">>> systemd-Service creabim-server installieren ..."
cat > /etc/systemd/system/creabim-server.service <<UNITEOF
[Unit]
Description=CreaBIM Server – lokale BIM-Web-App (FastAPI + creabim-cli)
Documentation=https://github.com/HatchetMan111/CreaBIM-Proxmox
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_ROOT}/src/backend
Environment=CREABIM_DATA_DIR=${APP_ROOT}/data
Environment=CREABIM_CLI=${APP_ROOT}/bin/creabim-cli
Environment=CREABIM_VERSION=${CREABIM_VERSION}
ExecStart=${APP_ROOT}/.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port ${PORT}
Restart=always
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable creabim-server >/dev/null 2>&1
systemctl restart creabim-server

echo ">>> Prüfe, dass der Server auf Port ${PORT} antwortet ..."
PORT_OK=""
for _ in $(seq 1 30); do
    if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:${PORT}/api/health"; then
        PORT_OK=1
        break
    fi
    sleep 1
done
if [ -z "$PORT_OK" ]; then
    die "creabim-server antwortet nicht auf Port ${PORT}.
  Letzte Logs:
$(journalctl -u creabim-server --no-pager 2>/dev/null | tail -n 25)"
fi

# ── systemd: GUI (optional) ────────────────────────────────────────────────
if [ "${INSTALL_GUI}" = "true" ]; then
    echo ">>> GUI-Pakete installieren (Xvfb, x11vnc, noVNC, GTK, WebKitGTK) ..."
    apt-get install -y -qq xvfb x11vnc novnc websockify openbox \
        x11-utils libgtk-3-0 libgl1-mesa-dri mesa-vulkan-drivers \
        fonts-dejavu-core || \
        die "GUI-Pakete konnten nicht installiert werden (apt-Ausgabe siehe oben)."
    if ! apt-get install -y -qq libwebkit2gtk-4.1-0 >/dev/null 2>&1; then
        die "libwebkit2gtk-4.1-0 ist in diesem Debian-Release nicht verfügbar.
  CreaBIM braucht WebKitGTK 4.1 – das gibt es in Debian 13 (trixie) und Ubuntu 24.04.
  Neu anlegen:  pct stop ${CT_ID:-<id>} && pct destroy ${CT_ID:-<id>} --purge
  und mit einem Debian-13-Template installieren (--gui)."
    fi

    NOVNC_DIR=$(dpkg -L novnc 2>/dev/null | grep -m1 '/vnc.html$' | xargs -r dirname)
    if [ -z "${NOVNC_DIR:-}" ] || [ ! -f "${NOVNC_DIR}/vnc.html" ]; then
        die "noVNC-Webroot nicht gefunden (Paket novnc installiert?)."
    fi
    echo "    noVNC unter ${NOVNC_DIR}"

    if [ -n "${GUI_PASSWORD:-}" ]; then
        printf '%s\n' "${GUI_PASSWORD}" > "${APP_ROOT}/.vncpass.txt"
    else
        printf '%s\n' "$(head -c 12 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 12)" \
            > "${APP_ROOT}/.vncpass.txt"
    fi
    chmod 600 "${APP_ROOT}/.vncpass.txt"
    chown "${APP_USER}:${APP_USER}" "${APP_ROOT}/.vncpass.txt"
    x11vnc -storepasswd "$(cat "${APP_ROOT}/.vncpass.txt")" "${APP_ROOT}/.vncpass" >/dev/null 2>&1 \
        || die "x11vnc-Passwortdatei konnte nicht erzeugt werden."
    chown "${APP_USER}:${APP_USER}" "${APP_ROOT}/.vncpass"
    mkdir -p "${APP_ROOT}/log"
    chown -R "${APP_USER}:${APP_USER}" "${APP_ROOT}/log"

    cat > "${APP_ROOT}/bin/creabim-gui.sh" <<GUIEOF
#!/usr/bin/env bash
# Startet CreaBIM unter Xvfb und reicht den Bildschirm per noVNC weiter.
# Läuft als systemd-Service creabim-gui; beendet alle Kinder beim Stop.
set -uo pipefail
export DISPLAY=:99
export LIBGL_ALWAYS_SOFTWARE=1
export GDK_BACKEND=x11
export WEBKIT_DISABLE_DMABUF_RENDERER=1
LOG=/opt/creabim/log/creabim-gui.log
PIDS=()
cleanup() {
    local p
    for p in "\${PIDS[@]:-}"; do
        kill "\$p" 2>/dev/null || true
    done
}
trap cleanup EXIT INT TERM

: "\${NOVNC_DIR:?NOVNC_DIR fehlt}"
: "\${GUI_PORT:?GUI_PORT fehlt}"

Xvfb :99 -screen 0 1600x1000x24 -ac +extension GLX +render -noreset >>"\$LOG" 2>&1 &
PIDS+=(\$!)
for _ in \$(seq 1 20); do
    xdpyinfo -display :99 >/dev/null 2>&1 && break
    sleep 0.5
done
xdpyinfo -display :99 >/dev/null 2>&1 || { echo "Xvfb startet nicht:"; tail -n 20 "\$LOG"; exit 1; }

command -v openbox >/dev/null && { openbox >>"\$LOG" 2>&1 & PIDS+=(\$!); }

/opt/creabim/bin/creabim >>"\$LOG" 2>&1 &
PIDS+=(\$!)

x11vnc -display :99 -forever -shared -rfbauth /opt/creabim/.vncpass \
    -rfbport 5900 -quiet >>"\$LOG" 2>&1 &
PIDS+=(\$!)
sleep 1

# websockify bleibt im Vordergrund – systemd überwacht genau diesen Prozess.
exec websockify --web="\$NOVNC_DIR" "${GUI_PORT}" localhost:5900
GUIEOF
    chmod 0755 "${APP_ROOT}/bin/creabim-gui.sh"

    cat > /etc/systemd/system/creabim-gui.service <<UNITEOF
[Unit]
Description=CreaBIM GUI – CreaBIM im Browser (noVNC)
Documentation=https://github.com/HatchetMan111/CreaBIM-Proxmox
After=network-online.target creabim-server.service
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
Environment=NOVNC_DIR=${NOVNC_DIR}
Environment=GUI_PORT=${GUI_PORT}
ExecStart=${APP_ROOT}/bin/creabim-gui.sh
Restart=always
RestartSec=8
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
UNITEOF

    systemctl daemon-reload
    systemctl enable creabim-gui >/dev/null 2>&1
    systemctl restart creabim-gui
    GUI_OK=""
    for _ in $(seq 1 20); do
        if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:${GUI_PORT}/vnc.html"; then
            GUI_OK=1
            break
        fi
        sleep 1
    done
    if [ -z "$GUI_OK" ]; then
        warn "noVNC antwortet (noch) nicht auf Port ${GUI_PORT}.
  Logs: journalctl -u creabim-gui -e && tail -n 30 /opt/creabim/log/creabim-gui.log"
    fi
fi

echo ">>> Aufräumen ..."
rm -rf /tmp/creabim-src /tmp/creabim-src.tar.gz /tmp/creabim.tar.gz /tmp/creabim-dist \
       /tmp/nodesource-setup.sh 2>/dev/null || true

echo ">>> Setup abgeschlossen."
INNEREOF
}

run_inner_setup() {
    local ct_id="$1"
    header "⚙️  Installiere CreaBIM im Container $ct_id"
    # DNS des Hosts in den Container bringen (dort resolvert das Setup garantiert)
    local host_dns
    host_dns=$(grep -h '^nameserver' /etc/resolv.conf 2>/dev/null \
               | awk '{print $2}' | grep -v '^127\.' | head -1 || true)
    write_inner_script
    pct push "$ct_id" "$TMP_DIR/setup-inner.sh" /root/setup-inner.sh
    # Variablen via env in den Container (kein Expansion-Heredoc → keine
    # Escaping-Gruben). set -o pipefail: ein Crash im Inner-Script darf nicht
    # durch `tee` maskiert werden.
    pct exec "$ct_id" -- env \
        PORT="$PORT" \
        GUI_PORT="$GUI_PORT" \
        INSTALL_GUI="$INSTALL_GUI" \
        CREABIM_TARBALL_URL="$CREABIM_TARBALL_URL" \
        CREABIM_SHA256="${CREABIM_SHA256:-}" \
        CREABIM_VERSION="$CREABIM_VERSION" \
        HOST_DNS="${host_dns:-1.1.1.1}" \
        UPSTREAM_TARBALL_URL="$UPSTREAM_TARBALL_URL" \
        NODE_MAJOR="$NODE_MAJOR" \
        APP_USER="$APP_NAME" \
        GUI_PASSWORD="${GUI_PASSWORD:-}" \
        bash -c 'set -o pipefail; bash /root/setup-inner.sh 2>&1 | tee /var/log/creabim-setup.log'
}

get_installed_version() {
    # Version aus der systemd-Umgebung (CREABIM_VERSION) – || true INNERHALB von
    # $() (Grube: pipefail + pct-exec-Fehlschlag würde die Substitution töten).
    local v=""
    v=$(pct exec "$1" -- sh -c 'systemctl show creabim-server -p Environment 2>/dev/null | tr " " "\n" | grep "^CREABIM_VERSION=" | cut -d= -f2-' 2>/dev/null | tail -n 1 || true)
    echo "$v"
}

# ── Verifikation ───────────────────────────────────────────────────────────
verify_installation() {
    local ct_id="$1" tries=0 code=""

    header "✅ Verifikation"

    # creabim-server aktiv?
    while true; do
        if pct exec "$ct_id" -- systemctl is-active --quiet creabim-server 2>/dev/null; then
            ok "Service creabim-server läuft (Web/API auf Port $PORT)"
            break
        fi
        tries=$((tries + 1))
        if [[ $tries -ge 30 ]]; then
            die "Service creabim-server läuft nicht.
  Debug: pct exec $ct_id -- journalctl -u creabim-server -e"
        fi
        sleep 1
    done

    # Health-API antwortet?
    tries=0
    while true; do
        code=$(pct exec "$ct_id" -- curl -s -o /dev/null --max-time 3 -w '%{http_code}' \
               "http://127.0.0.1:${PORT}/api/health" || true)
        if [[ "$code" == "200" ]]; then
            ok "API antwortet (HTTP 200 auf /api/health)"
            break
        fi
        tries=$((tries + 1))
        if [[ $tries -ge 30 ]]; then
            local diag
            diag=$(pct exec "$ct_id" -- sh -c '
                echo "--- Listener auf Port '"$PORT"' (ss -tlnp) ---"
                ss -tlnp 2>/dev/null | grep -E "[:.]'"$PORT"'" || echo "  (KEIN Listener auf Port '"$PORT"')"
                echo "--- journalctl -u creabim-server ---"
                journalctl -u creabim-server --no-pager 2>/dev/null | tail -n 12 || true
            ' 2>/dev/null || true)
            die "Web-UI antwortet nicht (letzter HTTP-Code: ${code:-unbekannt}).

${diag}
  Debug: pct exec $ct_id -- journalctl -u creabim-server -e"
        fi
        sleep 1
    done

    # Frontend ausgeliefert?
    if pct exec "$ct_id" -- test -f /opt/creabim/src/backend/static/index.html 2>/dev/null; then
        ok "Frontend vorhanden (/opt/creabim/src/backend/static/index.html)"
    else
        die "static/index.html fehlt im Container.
  Debug: pct exec $ct_id -- tail -n 40 /var/log/creabim-setup.log"
    fi

    # GUI (optional)?
    if $INSTALL_GUI; then
        if pct exec "$ct_id" -- systemctl is-active --quiet creabim-gui 2>/dev/null; then
            ok "Service creabim-gui läuft (noVNC auf Port $GUI_PORT)"
        else
            warn "Service creabim-gui läuft nicht – GUI wird nicht erreichbar sein.
  Logs: pct exec $ct_id -- journalctl -u creabim-gui -e"
        fi
    fi

    # Erreichbarkeit vom PROXMOX-HOST aus (die Nutzer-URL läuft über die CT-IP;
    # im CT-Loopback kann alles OK sein, während eine Firewall draußen blockt).
    local ct_ip="" host_code=""
    ct_ip=$(get_ct_ip "$ct_id")
    if [[ -n "$ct_ip" ]]; then
        host_code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 \
                    "http://${ct_ip}:${PORT}/api/health" || true)
        if [[ "$host_code" == "200" ]]; then
            ok "Vom Host erreichbar: http://${ct_ip}:${PORT} (HTTP 200)"
        else
            warn "Im CT OK, aber vom Proxmox-Host nicht erreichbar (HTTP ${host_code:-000} über http://${ct_ip}:${PORT})."
            info "Prüfe CT-Firewall (pct config $ct_id | grep -E 'net0|firewall') und Bridge-Setup."
        fi
    fi
}

# ── Zusammenfassung ────────────────────────────────────────────────────────
print_summary() {
    header "🏛️  CreaBIM Server ist bereit!"

    local ct_ip installed_version=""
    ct_ip=$(get_ct_ip "$CT_ID")
    if [[ -z "$ct_ip" ]]; then
        ct_ip="<IP-ADRESSE>"
    fi
    installed_version=$(get_installed_version "$CT_ID")

    echo ""
    echo -e "  ${GREEN}${BOLD}════════════════════════════════════════════════════════════${NC}"
    echo -e "  ${GREEN}  🌐 Web-UI:     http://${ct_ip}:${PORT}${NC}"
    if $INSTALL_GUI; then
        echo -e "  ${GREEN}  🖥️  GUI (noVNC): http://${ct_ip}:${GUI_PORT}/vnc.html${NC}"
    fi
    echo -e "  ${GREEN}  🐚 Terminal:   pct enter ${CT_ID}${NC}"
    if [[ -n "$CT_PASSWORD" ]]; then
        echo -e "  ${GREEN}  🔑 Root-PW:    ${CT_PASSWORD}${NC}"
    fi
    if $INSTALL_GUI && [[ -n "${GUI_PASSWORD:-}" ]]; then
        echo -e "  ${GREEN}  🔑 VNC-PW:     ${GUI_PASSWORD}${NC}"
    fi
    if [[ -n "$installed_version" ]]; then
        echo -e "  ${GREEN}  📦 CreaBIM:    ${installed_version} (Release ${CREABIM_OWNER}/${CREABIM_REPO})${NC}"
    fi
    echo -e "  ${GREEN}  🔧 Installer:  v${INSTALLER_VERSION}${NC}"
    echo -e "  ${GREEN}${BOLD}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "  ${CYAN}Sobald die App läuft:${NC}"
    echo "  1. http://${ct_ip}:${PORT} öffnen"
    echo "  2. Projekt anlegen oder eine .ifc-Datei importieren"
    echo "  3. Grundrisse, Schnitte und Pläne rendern und als PDF/IFC exportieren"
    echo ""
    echo -e "  ${CYAN}Nützliche Befehle (exakt kopierbar):${NC}"
    echo "  Status:    ${ONE_LINER} --status"
    echo "  Update:    ${ONE_LINER} --update"
    echo "  Deinstall: ${ONE_LINER} --uninstall"
    echo "  Logs:      pct exec ${CT_ID} -- journalctl -u creabim-server -f"
    echo ""
    if $INSTALL_GUI; then
        warn "Die noVNC-GUI läuft per Software-Rendering (llvmpipe) – für flüssiges"
        warn "3D ist eine VM mit GPU-Passthrough deutlich besser geeignet."
    fi
    warn "CreaBIM ist ein nativer Modellierer; der Server stellt Plan-, Schnitt- und"
    warn "Export-Funktionen bereit. Für interaktives Modellieren --gui verwenden."
}

# ── Install ────────────────────────────────────────────────────────────────
do_install() {
    header "🏛️  Installiere ${APP_PRETTY} (LXC)"
    info "Installer-Version: v${INSTALLER_VERSION}"
    $INSTALL_GUI && info "GUI-Modus: CreaBIM zusätzlich über noVNC (Port $GUI_PORT)"

    if [[ $EUID -ne 0 ]]; then
        die "Bitte als root ausführen (auf dem Proxmox-Host)."
    fi
    if ! command -v pct >/dev/null 2>&1; then
        die "pct nicht gefunden – das Script muss auf einem Proxmox-VE-Host laufen."
    fi

    # Bereits vorhanden?
    local existing
    existing=$(find_ct_id_by_hostname || true)
    if [[ -n "$existing" ]]; then
        if $FORCE_RECREATE; then
            warn "Container $existing ($CT_HOSTNAME) existiert – --force: lösche und lege neu an."
            pct stop "$existing" || true
            pct destroy "$existing" --purge
        else
            die "Container $existing mit Hostname '$CT_HOSTNAME' existiert bereits.
  Update:         ${ONE_LINER} --update
  Neu aufsetzen:  ${ONE_LINER} --force"
        fi
    fi

    # Template: headless genügt Debian 12; für WebKitGTK 4.1 muss es Debian 13 sein.
    header "🧱 Container-Template"
    local template=""
    if $INSTALL_GUI; then
        template=$(ensure_template 13 || true)
        if [[ -z "$template" ]]; then
            template=$(ensure_template 12 || true)
            if [[ -n "$template" ]]; then
                warn "Debian 13 (mit WebKitGTK 4.1) ist nicht verfügbar – Fallback auf Debian 12."
                warn "Die GUI kann dort fehlen; der Server funktioniert weiterhin."
            fi
        fi
    else
        template=$(ensure_template 12 || true)
        [[ -z "$template" ]] && template=$(ensure_template 13 || true)
    fi
    if [[ -z "$template" ]]; then
        die "Kein Debian-Template verfügbar.
  Prüfe: pveam available | grep debian"
    fi
    ok "Template: $template"

    # Release auflösen (SHA-256 für den Download)
    resolve_release

    # ID & Passwort
    if [[ -z "$CT_ID" ]]; then
        CT_ID=$(find_free_id)
        info "Nächste freie CT-ID: $CT_ID"
    fi
    if [[ -z "$CT_PASSWORD" ]]; then
        CT_PASSWORD=$(openssl rand -base64 12 2>/dev/null || true)
        if [[ -z "$CT_PASSWORD" ]]; then
            CT_PASSWORD="creabim-$(date +%s)"
        fi
    fi
    # VNC-Passwort für noVNC erzeugen – wir zeigen es am Ende an, also muss es
    # hier feststehen (sonst würde es nur im Container liegen).
    if $INSTALL_GUI && [[ -z "$GUI_PASSWORD" ]]; then
        GUI_PASSWORD=$(openssl rand -base64 18 2>/dev/null | tr -dc 'A-Za-z0-9' | head -c 16)
        if [[ -z "$GUI_PASSWORD" ]]; then
            GUI_PASSWORD="creabim-$(date +%s)"
        fi
    fi

    # Container anlegen
    header "🚀 Erzeuge Container $CT_ID ($CT_HOSTNAME)"
    local net0="name=eth0,bridge=${CT_BRIDGE},ip=${CT_IP},firewall=0"
    if [[ -n "$CT_GATEWAY" ]]; then
        net0+=",gateway=${CT_GATEWAY}"
    fi
    local ssh_keys_args=()
    if [[ -n "$CT_SSHKEY" ]]; then
        if [[ "$CT_SSHKEY" == http://* || "$CT_SSHKEY" == https://* ]]; then
            info "Lade SSH-Public-Key herunter ..."
            wget -q --tries=3 -O "$TMP_DIR/sshkey.pub" "$CT_SSHKEY" || die "SSH-Key-URL nicht ladbar: $CT_SSHKEY"
        elif [[ -f "$CT_SSHKEY" ]]; then
            cp "$CT_SSHKEY" "$TMP_DIR/sshkey.pub"
        else
            die "SSH-Key-Datei nicht gefunden: $CT_SSHKEY"
        fi
        if [[ ! -s "$TMP_DIR/sshkey.pub" ]]; then
            die "SSH-Key-Datei ist leer: $CT_SSHKEY"
        fi
        SSH_KEY_FILE="$TMP_DIR/sshkey.pub"
        ok "SSH-Public-Key wird in den Container installiert (ssh-key-Login als root)"
        ssh_keys_args=(--ssh-public-keys "$SSH_KEY_FILE")
    fi
    pct create "$CT_ID" "$template" \
        --hostname "$CT_HOSTNAME" \
        --cores "$CT_CORES" \
        --memory "$CT_MEMORY" \
        --swap "$CT_SWAP" \
        --rootfs "${CT_STORAGE}:${CT_ROOTFS}" \
        --net0 "$net0" \
        --unprivileged 1 \
        --onboot 1 \
        --start 1 \
        --password "$CT_PASSWORD" \
        "${ssh_keys_args[@]}"
    ok "Container $CT_ID erstellt und gestartet"

    wait_for_ct_network "$CT_ID"
    verify_ct_dns "$CT_ID"

    run_inner_setup "$CT_ID"
    verify_installation "$CT_ID"
    print_summary
}

# ── Update ─────────────────────────────────────────────────────────────────
do_update() {
    header "🔄 Update ${APP_PRETTY}"

    local ct_id
    ct_id=$(find_ct_id_by_hostname || true)
    if [[ -z "$ct_id" ]]; then
        die "Kein Container mit Hostname '$CT_HOSTNAME' gefunden.
  Erst installieren:  ${ONE_LINER}"
    fi
    CT_ID="$ct_id"

    ensure_ct_running "$ct_id"
    verify_ct_dns "$ct_id"
    resolve_release

    # VNC-Passwort beim Update beibehalten, nicht stillrotieren.
    if [[ -z "$GUI_PASSWORD" ]]; then
        GUI_PASSWORD=$(pct exec "$ct_id" -- cat /opt/creabim/.vncpass.txt 2>/dev/null | head -1 || true)
    fi

    run_inner_setup "$ct_id"
    verify_installation "$ct_id"

    ok "Update abgeschlossen – Projekte und Job-Artefakte blieben erhalten."
    print_summary
}

# ── Uninstall ──────────────────────────────────────────────────────────────
do_uninstall() {
    header "🗑️  Deinstalliere ${APP_PRETTY}"

    local ct_id
    ct_id=$(find_ct_id_by_hostname || true)
    if [[ -z "$ct_id" ]]; then
        warn "Kein Container mit Hostname '$CT_HOSTNAME' gefunden – nichts zu tun."
        return 0
    fi
    CT_ID="$ct_id"

    warn "Container $ct_id ($CT_HOSTNAME) wird GESTOPPT und GELÖSCHT."
    warn "Projekte, Importe und Job-Artefakte liegen im Container – sie gehen verloren."
    if ! $ASSUME_YES; then
        local answer=""
        if ! read -r -t 60 -p "Wirklich löschen? (ja/NEIN): " answer; then
            die "Keine Bestätigung erhalten (nicht-interaktiv?) – nichts gelöscht.
  Erzwingen:  ${ONE_LINER} --uninstall --yes"
        fi
        if [[ "$answer" != "ja" ]]; then
            info "Abgebrochen – nichts gelöscht."
            return 0
        fi
    fi
    pct stop "$ct_id" || true
    pct destroy "$ct_id" --purge
    ok "Container $ct_id gelöscht."
}

# ── Status ─────────────────────────────────────────────────────────────────
do_status() {
    header "📊 Status ${APP_PRETTY}"
    info "Installer-Version: v${INSTALLER_VERSION}"

    local ct_id
    ct_id=$(find_ct_id_by_hostname || true)
    if [[ -z "$ct_id" ]]; then
        warn "Kein Container mit Hostname '$CT_HOSTNAME' gefunden."
        info "Installieren:  ${ONE_LINER}"
        return 0
    fi
    CT_ID="$ct_id"

    # Gestoppten CT nicht als "läuft nicht" fehldeklarieren
    local state
    state=$(pct status "$ct_id" 2>/dev/null | awk '{print $2}' || true)

    pct list 2>/dev/null | awk -v id="$ct_id" -v st="$state" '$1==id {print "Container:  " $1 " (" $2 ") – " st}'

    if [[ "$state" != "running" ]]; then
        warn "Container $ct_id ist nicht gestartet (${state:-unbekannt}) – Service/Version/Web-UI ohne Start nicht prüfbar."
        info "Starten:    pct start $ct_id"
        return 0
    fi

    if pct exec "$ct_id" -- systemctl is-active --quiet creabim-server 2>/dev/null; then
        ok "Service:   creabim-server läuft (Web/API auf Port $PORT)"
    else
        err "Service:   creabim-server läuft NICHT"
        info "Logs:      pct exec $ct_id -- journalctl -u creabim-server -e"
    fi

    if pct exec "$ct_id" -- systemctl is-active --quiet creabim-gui 2>/dev/null; then
        ok "Service:   creabim-gui läuft (noVNC auf Port $GUI_PORT)"
    elif pct exec "$ct_id" -- test -f /etc/systemd/system/creabim-gui.service 2>/dev/null; then
        err "Service:   creabim-gui ist installiert, läuft aber NICHT"
        info "Logs:      pct exec $ct_id -- journalctl -u creabim-gui -e"
    fi

    local installed_version=""
    installed_version=$(get_installed_version "$ct_id")
    if [[ -n "$installed_version" ]]; then
        info "Version:   ${installed_version} (Server-Code: ${UPSTREAM_OWNER}/${UPSTREAM_REPO}@${UPSTREAM_BRANCH})"
    else
        warn "Version:   nicht ermittelbar (App installiert?)"
    fi

    local ip code="" projects=""
    ip=$(get_ct_ip "$ct_id")
    if [[ -n "$ip" ]]; then
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://${ip}:${PORT}/api/health" || true)
        if [[ "$code" == "200" ]]; then
            ok "Web-UI:    http://${ip}:${PORT}  (HTTP 200)"
        else
            warn "Web-UI:    HTTP-Code ${code:-unbekannt} von http://${ip}:${PORT}"
        fi
        projects=$(curl -s --max-time 5 "http://${ip}:${PORT}/api/projects" 2>/dev/null \
                   | grep -o '"id"' | wc -l || true)
        # if statt [[ ]] && – sonst ist die letzte Zeile der Funktion 1 (Fehlerkaskade)
        if [[ "${projects:-0}" -gt 0 ]]; then
            info "Projekte:  ${projects}"
        fi
    else
        warn "Container hat keine IP (läuft er?)."
    fi
}

# ── Main ───────────────────────────────────────────────────────────────────
parse_args "$@"

TMP_DIR=$(mktemp -d)

if $UNINSTALL; then
    do_uninstall
elif $UPDATE; then
    do_update
elif $STATUS_CHECK; then
    do_status
else
    do_install
fi