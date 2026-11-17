# 🏛️ CreaBIM Server – Proxmox-Installer

Lokale BIM-Web-App im LXC: Projekte verwalten, Grundrisse, Schnitte, Ansichten und
Pläne rendern und als **PDF, IFC4, IFC5, XLSX, CSV, glTF (Blender) oder FreeCAD**
exportieren – vollständig offline, ohne Cloud, ohne Konto.

Der Server ist die Web-Hülle um die headless [`creabim-cli`](https://github.com/chopinregis/CreaBIM)
von **CreaBIM** (GPL-3.0): einem nativen BIM-Modellierer für Architekten, der ein
Modell für 3D, Pläne, Schnitte, Ansichten, Blätter, Stücklisten, Mengen und IFC
gemeinsam führt.

```
┌──────────────────────────── LXC (unprivilegiert) ────────────────────────────┐
│  React/Vite-SPA  ──►  FastAPI  ──►  creabim-cli  ──►  Modell / SVG / PDF …   │
│        (Browser)      (Port 8030)     (SHA-256-geprüft)                      │
│                                                                              │
│  optional (--gui):  Xvfb + CreaBIM-GUI + x11vnc + noVNC  (Port 8031)        │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Installation (Einzeiler auf dem Proxmox-Host)

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/CreaBIM-Proxmox/main/install/creabim.sh)"
```

Danach ist die Weboberfläche erreichbar unter **`http://<CT-IP>:8030`**.
Die fertige URL, das Root-Passwort und alle Folgekommandos stehen am Ende der
Ausgabe.

### Optionen

Optionen kommen hinter das schließende Anführungszeichen:

```bash
bash -c "$(wget -qLO - …/install/creabim.sh)" -- --id 210 --memory 4096 --gui
```

| Option | Bedeutung | Default |
|---|---|---|
| `--id ID` | Container-ID | nächste freie ab 200 |
| `--hostname NAME` | Hostname | `creabim` |
| `--storage NAME` | Storage für die rootfs | `local-lvm` |
| `--rootfs GB` | Plattengröße | 6 (mit `--gui` 10) |
| `--cores N` | vCPUs | 2 |
| `--memory MB` | RAM | 2048 (mit `--gui` 4096) |
| `--swap MB` | Swap | 1024 (mit `--gui` 2048) |
| `--bridge BR` | Netzwerk-Bridge | `vmbr0` |
| `--ip CIDR` | statische IP statt DHCP | `dhcp` |
| `--gateway GW` | Gateway bei statischer IP | – |
| `--password PW` | Root-Passwort im CT | automatisch |
| `--sshkey PFAD\|URL` | Public Key für root | – |
| `--port PORT` | Web-UI-Port | `8030` |
| `--gui` | CreaBIM-GUI zusätzlich über noVNC | aus |
| `--gui-port PORT` | noVNC-Port | `8031` |
| `--gui-password PW` | VNC-Passwort | automatisch |
| `--force` | vorhandenen CT löschen und neu anlegen | – |
| `--yes` / `-y` | Rückfragen überspringen | – |

### Verwaltung

```bash
# Status (Service, Version, Web-UI, Projektanzahl)
bash -c "$(wget -qLO - …/install/creabim.sh)" -- --status

# Update: neues CreaBIM-Release + neuer Server-Code, Projekte bleiben
bash -c "$(wget -qLO - …/install/creabim.sh)" -- --update

# Deinstallieren (löscht Container inkl. Projekte)
bash -c "$(wget -qLO - …/install/creabim.sh)" -- --uninstall
```

## Was die App kann

| Bereich | Funktionen |
|---|---|
| **Projekte** | Beispielmodelle (6 Stück), Import von `.ifc`, `.ifcx`, `.creabim`, `.creabim.json`, Umbenennen, Modell-Download |
| **Zeichnungen** | Grundrisse, Schnitte, Ansichten und einzelne Pläne als Vektor-SVG – direkt im Browser |
| **Export** | Alle Pläne als PDF, Excel-Schedules, CSV-Listen, IFC4, IFC5 (IFCX), glTF/GLB für Blender, FreeCAD |
| **Auswertung** | Element-Statistik nach IFC-Klasse, Modellprüfung (Türen/Wandanschlüsse), Beschriftungs-Konflikte, Räume aus Notizen |

Die App ist bewusst eine **Werkbank um die CLI**: interaktiv modellieren lässt
sich mit CreaBIM selbst – dafür ist der optionale GUI-Modus da.

## GUI-Modus (optional)

Mit `--gui` läuft zusätzlich das echte CreaBIM-Fenster in einer virtuellen
X11-Sitzung und wird per **noVNC** im Browser ausgeliefert
(`http://<CT-IP>:8031/vnc.html`, VNC-Passwort steht in der Installationsausgabe).

```bash
bash -c "$(wget -qLO - …/install/creabim.sh)" -- --gui
```

Wichtige Hinweise:

* Die GUI braucht **WebKitGTK 4.1** – das liefert Debian 13 (trixie) oder
  Ubuntu 24.04. Der Installer wählt das Template automatisch; auf Debian 12
  bricht die Installation mit einer klaren Meldung ab.
* Im LXC rendert CreaBIM über **Software (llvmpipe)**. Für flüssiges Arbeiten in
  3D ist eine **VM mit GPU-Passthrough** (`/dev/dri`) deutlich besser geeignet.
* Der noVNC-Port ist durch ein VNC-Passwort geschützt, aber **nicht** durch
  TLS. Wer die GUI von außerhalb des LANs nutzt, sollte einen Reverse-Proxy
  mit TLS davorsetzen.

## Projektstruktur

```
CreaBIM-Proxmox/
├── install/creabim.sh              # Einzeiler-Installer (Community-Scripts-Stil)
├── app/
│   ├── backend/
│   │   ├── main.py                 # FastAPI: API + SPA
│   │   ├── creabim_cli.py          # Wrapper um creabim-cli (Aktionen, Fehlerketten)
│   │   ├── library.py              # Projekte, Import, Struktur-Cache
│   │   ├── jobs.py                 # Hintergrund-Jobs + Artefakte
│   │   └── static/                 # gebautes React/Vite-Frontend
│   └── frontend/                   # React/Vite-Quelle
├── systemd/
│   ├── creabim-server.service
│   └── creabim-gui.service
└── test/
    ├── test_api.py                 # API-Tests gegen eine Stub-CLI
    ├── test_real_cli.py            # Integrationstests gegen das echte Binary
    └── harness/run-harness.sh      # Installer-Harness mit pct/pveam-Attrappen
```

## Entwicklung & Tests

```bash
# Backend-Tests (Stub-CLI, schnell)
pytest test/ -q

# Integrationstests gegen ein echtes CreaBIM-Release
CREABIM_TEST_CLI=/opt/creabim/bin/creabim-cli pytest test/ -q

# Installer-Harness (Attrappen für pct/pveam/curl, läuft ohne Proxmox)
bash test/harness/run-harness.sh
```

Das Frontend wird mit Node 22 gebaut und nach `app/backend/static` geschrieben:

```bash
cd app/frontend && npm ci && npm run build
```

## Fehlersuche

Der Installer gibt bei Fehlern die **komplette Kette** aus: Zeile, Befehl,
Exit-Code, letzte Logzeilen und die Container-Logs. Zusätzlich liegt das
vollständige Log unter `/tmp/creabim-installer-<zeitstempel>.log`.

```bash
# Voller bash -x-Trace
bash -c "$(wget -qLO - …/install/creabim.sh)" -- --debug

# Service-Logs im Container
pct exec creabim -- journalctl -u creabim-server -e
pct exec creabim -- journalctl -u creabim-gui -e
tail -n 50 /opt/creabim/log/creabim-gui.log
```

| Symptom | Ursache / Lösung |
|---|---|
| `DNS im Container defekt` | Der Installer schreibt Fallback-Nameserver; prüfen mit `pct exec creabim -- cat /etc/resolv.conf` |
| `Web-UI antwortet nicht` | `journalctl -u creabim-server -e` im Container; meist fehlende Python-Abhängigkeit |
| `libwebkit2gtk-4.1-0 ist nicht verfügbar` | Debian 12 – für die GUI ein Debian-13-Template verwenden |
| noVNC bleibt schwarz | Software-Rendering ist langsam; `tail -n 50 /opt/creabim/log/creabim-gui.log` |
| `CREABIM_SHA256` fehlt | Das Release hat keine `SHA256SUMS.txt` – der Installer warnt und überspringt die Prüfung |

## API

Die Weboberfläche nutzt eine kleine JSON-API (FastAPI, OpenAPI unter
`/api/docs`):

```
GET  /api/health                     Status + CLI-Pfad
GET  /api/info                       Aktionen, Beispielmodelle, Version
GET  /api/projects                   Projektliste
POST /api/projects                   Projekt aus Beispiel anlegen
POST /api/projects/import            Datei hochladen (.ifc/.ifcx/.creabim/.json)
GET  /api/projects/{id}              Projekt + Struktur
GET  /api/projects/{id}/structure    Geschosse, Ansichten, Pläne, Statistik
GET  /api/projects/{id}/model        Modelldatei herunterladen
POST /api/projects/{id}/jobs         Aktion starten (plan, view, pdf, ifc, …)
GET  /api/jobs[/{id}]                Jobs + Status
GET  /api/jobs/{id}/artifact         Ergebnis herunterladen (auch inline)
GET  /api/jobs/{id}/report           vollständige Fehlerkette
```

## Credits & Lizenz

* **CreaBIM** von Regis Benoit Brice Nde Tene – GPL-3.0-or-later,
  <https://github.com/chopinregis/CreaBIM>. Der Installer lädt das offizielle
  Release herunter und prüft die SHA-256-Summe; es wird nichts verändert.
* Installer, Server-Code und Weboberfläche: MIT (siehe [LICENSE](LICENSE)).

CreaBIM ist ausdrücklich „ready to explore, not yet for production work" –
siehe die bekannten Lücken im Upstream-Projekt.