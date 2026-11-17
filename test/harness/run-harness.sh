#!/usr/bin/env bash
# =============================================================================
#  Mock-Harness für install/creabim.sh
#
#  Führt den Installer OHNE Proxmox aus: pct/pveam/curl/openssl werden durch
#  Attrappen ersetzt, die Aufrufe protokollieren und einen Container spielen.
#  So lassen sich Create-Argumente, ID-Vergabe, Setup-Übergabe, Verifikation
#  und Zusammenfassung automatisiert prüfen.
#
#  Aufruf:  bash test/harness/run-harness.sh [--keep]
# =============================================================================
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
INSTALLER="$REPO/install/creabim.sh"

# Der Installer verlangt root (EUID 0). In der Sandbox ohne sudo:
# `unshare -rm` mappt den Nutzer auf root – so läuft der Harness überall.
if [[ "$(id -u)" -ne 0 ]]; then
    if command -v unshare >/dev/null 2>&1 && unshare -rm true 2>/dev/null; then
        exec unshare -rm bash "$0" "$@"
    fi
    printf '✘ Harness braucht root-Rechte (oder unshare -rm): bitte mit sudo starten.\n' >&2
    exit 1
fi

# Phils Profil exportiert grep als ugrep-Funktion – im Harness stört das.
unset -f grep 2>/dev/null || true

PASS=0
FAIL=0
KEEP="${1:-}"

say()  { printf '%s\n' "$*"; }
step() { printf '\n\033[0;34m▶ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[0;32m✔\033[0m %s\n' "$*"; PASS=$((PASS + 1)); }
bad()  { printf '  \033[0;31m✘\033[0m %s\n' "$*"; FAIL=$((FAIL + 1)); }

check()   { local d="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi; }
has()     { grep -qF -- "$2" "$1"; }
hasre()   { grep -qE -- "$2" "$1"; }

# ── Sandbox vorbereiten ────────────────────────────────────────────────────
ROOT=$(mktemp -d "${TMPDIR:-/tmp}/creabim-harness.XXXXXX")
cleanup() {
    if [[ "$KEEP" == "--keep" ]]; then
        say ""
        say "Sandbox bleibt erhalten: $ROOT"
    else
        rm -rf "$ROOT"
    fi
}
trap cleanup EXIT

FAKEBIN="$ROOT/bin"
mkdir -p "$FAKEBIN"
for tool in pct pveam curl openssl; do
    ln -sf "$HERE/mocks/$tool" "$FAKEBIN/$tool"
done

# Ein Lauf des Installers in einer eigenen Sandbox.
# $1 = Name, Rest = Argumente an den Installer
run_installer() {
    local name="$1"; shift
    local state="$ROOT/state-$name"
    mkdir -p "$state"
    touch "$state/pct.log" "$state/pveam.log" "$state/curl.log"
    (
        cd "$REPO" || exit 1
        MOCK_STATE="$state" \
        PATH="$FAKEBIN:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
            bash "$INSTALLER" "$@"
    ) >"$state/out.log" 2>&1
    echo "$?"
}

# ── 1. Syntax ──────────────────────────────────────────────────────────────
step "Syntaxprüfung"
check "bash -n install/creabim.sh" bash -n "$INSTALLER"
check "keine CRLF-Zeilen" bash -c "! grep -q $'\r' '$INSTALLER'"

# ── 2. Normalfall ──────────────────────────────────────────────────────────
step "Installation (Normalfall)"
RC=$(run_installer normal --yes)
S="$ROOT/state-normal"
check "Exit-Code 0" test "$RC" -eq 0
if [[ "$RC" -ne 0 ]]; then
    say "--- Ausgabe ---"
    tail -n 40 "$S/out.log" | sed 's/^/    /'
fi

check "Container wurde erzeugt" test -f "$S/ct-created"
CT_ID=$(cat "$S/ct-created" 2>/dev/null || echo "")
check "nächste freie ID = 200 (199 ist belegt)" test "$CT_ID" = "200"

if [[ -f "$S/create.args" ]]; then
    ARGS=$(cat "$S/create.args")
    check "unprivilegiert" bash -c "grep -q -- '--unprivileged 1' <<<'$ARGS'"
    check "onboot=1" bash -c "grep -q -- '--onboot 1' <<<'$ARGS'"
    check "hostname creabim" bash -c "grep -q -- '--hostname creabim' <<<'$ARGS'"
    check "2 vCPU" bash -c "grep -q -- '--cores 2' <<<'$ARGS'"
    check "2048 MB RAM" bash -c "grep -q -- '--memory 2048' <<<'$ARGS'"
    check "rootfs 6 GB" bash -c "grep -qE -- '--rootfs local-lvm:6' <<<'$ARGS'"
    check "Bridge vmbr0" bash -c "grep -q -- 'bridge=vmbr0' <<<'$ARGS'"
    check "DHCP-IP" bash -c "grep -q -- 'ip=dhcp' <<<'$ARGS'"
    check "Passwort gesetzt" bash -c "grep -q -- '--password TestPasswort1234' <<<'$ARGS'"
else
    bad "pct-create-Argumente wurden nicht protokolliert"
fi

check "Setup-Script in den Container geschoben" test -f "$S/pushed-inner.sh"
if [[ -f "$S/exec.env" ]]; then
    ENV_=$(tr '\n' ' ' <"$S/exec.env")
    check "PORT=8030 übergeben" bash -c "grep -qF -- 'PORT=8030' <<<'$ENV_'"
    check "INSTALL_GUI=false übergeben" bash -c "grep -qF -- 'INSTALL_GUI=false' <<<'$ENV_'"
    check "Release-URL übergeben" bash -c "grep -qF -- 'linux-x64.tar.gz' <<<'$ENV_'"
    check "SHA-256 übergeben" bash -c "grep -qF -- 'CREABIM_SHA256=0123456789abcdef' <<<'$ENV_'"
else
    bad "exec.env fehlt – pct exec wurde nicht wie erwartet aufgerufen"
fi

check "zusammengefasste URL im Log" has "$S/out.log" "http://10.120.1.77:8030"
check "Erfolgsmeldung im Log" has "$S/out.log" "CreaBIM Server ist bereit"
check "Update-Einzeiler im Log" has "$S/out.log" "--update"
check "Uninstall-Einzeiler im Log" has "$S/out.log" "--uninstall"

if [[ -f "$S/pushed-inner.sh" ]]; then
    INNER="$S/pushed-inner.sh"
    check "Inner-Script ist syntaktisch gültig" bash -n "$INNER"
    check "Inner-Script nutzt creabim-cli" has "$INNER" "bin/creabim-cli"
    check "Inner-Script kennt SHA-256-Prüfung" has "$INNER" "sha256sum -c"
    check "Inner-Script installiert systemd-Unit" has "$INNER" "creabim-server.service"
    check "Inner-Script bindet 0.0.0.0" has "$INNER" "--host 0.0.0.0"
    check "Inner-Script aktiviert Boot-Start" has "$INNER" "systemctl enable creabim-server"
    check "GUI-Teil ist eingeklammert" has "$INNER" 'if [ "${INSTALL_GUI}" = "true" ]'
fi

# ── 3. Zweiter Lauf (Idempotenz) ───────────────────────────────────────────
step "Zweiter Lauf ohne --force"
cp -f "$S/ct-created" "$S/ct-created.bak"
RC=$(run_installer normal --yes)
check "Lauf 2 scheitert mit Hinweis" test "$RC" -ne 0
check "Meldung 'existiert bereits'" has "$S/out.log" "existiert bereits"
check "Container nicht doppelt angelegt" test "$(wc -l <"$S/pct.log")" -ge 3

# ── 4. --status ────────────────────────────────────────────────────────────
step "--status"
mkdir -p "$ROOT/state-status"
echo "200" >"$ROOT/state-status/ct-created"
MOCK_STATE="$ROOT/state-status" \
PATH="$FAKEBIN:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    bash "$INSTALLER" --status >"$ROOT/state-status/out.log" 2>&1
RC=$?
check "Status-Exit 0" test "$RC" -eq 0
check "Status zeigt Service" has "$ROOT/state-status/out.log" "creabim-server läuft"
check "Status zeigt Web-UI" has "$ROOT/state-status/out.log" "HTTP 200"

# ── 5. --uninstall ─────────────────────────────────────────────────────────
step "--uninstall --yes"
mkdir -p "$ROOT/state-uninstall"
echo "200" >"$ROOT/state-uninstall/ct-created"
MOCK_STATE="$ROOT/state-uninstall" \
PATH="$FAKEBIN:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    bash "$INSTALLER" --uninstall --yes >"$ROOT/state-uninstall/out.log" 2>&1
RC=$?
check "Uninstall-Exit 0" test "$RC" -eq 0
check "pct destroy wurde gerufen" has "$ROOT/state-uninstall/pct.log" "destroy 200"
check "Container ist weg" test ! -f "$ROOT/state-uninstall/ct-created"

# ── 6. --gui ───────────────────────────────────────────────────────────────
step "Installation mit --gui"
RC=$(run_installer gui --yes --gui)
G="$ROOT/state-gui"
check "GUI-Exit-Code 0" test "$RC" -eq 0
if [[ -f "$G/create.args" ]]; then
    GARGS=$(cat "$G/create.args")
    check "GUI: 4096 MB RAM" bash -c "grep -q -- '--memory 4096' <<<'$GARGS'"
    check "GUI: 10 GB rootfs" bash -c "grep -q -- '--rootfs local-lvm:10' <<<'$GARGS'"
    check "GUI: Debian-13-Template" bash -c "grep -q 'debian-13' <<<'$GARGS'"
fi
check "GUI: GUI_PORT übergeben" has "$G/exec.env" "GUI_PORT=8031"
check "GUI: INSTALL_GUI=true" has "$G/exec.env" "INSTALL_GUI=true"
check "GUI: noVNC-URL im Log" has "$G/out.log" "vnc.html"
check "GUI: VNC-Passwort wird angezeigt" has "$G/out.log" "VNC-PW:"
if [[ -f "$G/pushed-inner.sh" ]]; then
    check "GUI: x11vnc im Inner-Script" has "$G/pushed-inner.sh" "x11vnc"
    check "GUI: websockify im Inner-Script" has "$G/pushed-inner.sh" "websockify"
    check "GUI: WebKitGTK 4.1" has "$G/pushed-inner.sh" "libwebkit2gtk-4.1-0"
    check "GUI: VNC-Passwort wird erzeugt" has "$G/pushed-inner.sh" "storepasswd"
fi

# ── 7. --help ──────────────────────────────────────────────────────────────
step "--help"
bash "$INSTALLER" --help >"$ROOT/help.log" 2>&1
check "Hilfe zeigt Einzeiler" has "$ROOT/help.log" 'bash -c "$(wget -qLO -'
check "Hilfe erklärt --gui" has "$ROOT/help.log" "--gui"

# ── Ergebnis ───────────────────────────────────────────────────────────────
printf '\n\033[1mErgebnis: %d grün, %d rot\033[0m\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]