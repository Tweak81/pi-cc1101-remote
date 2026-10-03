# Pi Zero 2 W + E07-M1101D: RF Logger

Dieses Werkzeug empfängt 433-MHz-Funkfernbedienungen und unterstützt einen passiven
RAW-Empfang für mehrere Fahrzeug-Protokollfamilien. Die bestehende Fernbedienungsaufnahme und das
Senden statischer Festcode-Aufnahmen bleiben verfügbar. Im Fahrzeugmodus ist Senden
in der Oberfläche und im Web-Endpunkt gesperrt. Es ist auf das fotografierte
**E07-M1101D, 433M V2.0** und Raspberry Pi Zero 2 W abgestimmt.

## Verdrahtung

Bei Draufsicht wie auf dem Foto (Antenne oben) ist Pin 1 unten links, Pin 2 darüber;
Pin 7 ist unten rechts, Pin 8 darüber.

```text
Bauteilseite, Antenne oben

        ANTENNE
     ┌───────────┐
oben │ 2  4  6  8│
unten│ 1  3  5  7│
     └───────────┘
```

Beim Blick auf die **Rückseite** ist die Reihenfolge horizontal gespiegelt:
oben `8 6 4 2`, unten `7 5 3 1`. Die aufgedruckten Ecknummern sind deshalb
wichtiger als die Blickrichtung.

| Modul | Funktion | Raspberry Pi Zero 2 W |
|---:|---|---|
| 1 | GND | Pin 6, GND |
| 2 | VCC | Pin 1, 3V3 |
| 3 | GDO0 / Sendedaten | Pin 18, GPIO24 |
| 4 | CSN | Pin 24, GPIO8 / CE0 |
| 5 | SCK | Pin 23, GPIO11 / SCLK |
| 6 | MOSI | Pin 19, GPIO10 / MOSI |
| 7 | MISO/GDO1 | Pin 21, GPIO9 / MISO |
| 8 | GDO2 / Empfangsdaten | Pin 22, GPIO25 |

**Niemals Pin 2 an 5 V anschließen.** Das Modul arbeitet mit 1,8–3,6 V. Vor dem
Verdrahten den Pi vollständig ausschalten. Leitungen möglichst kurz halten.

## Neuinstallation auf Raspberry Pi OS

Vor dem ersten Start Raspberry Pi OS (64-bit) mit Raspberry Pi Imager auf die
SD-Karte schreiben und dort zunächst das Heim-WLAN sowie einen Benutzernamen
einrichten. Der Pi benötigt diese Verbindung einmalig, um Pakete und das öffentliche
GitHub-Repository zu laden. Danach per SSH verbinden. Ein GitHub-Token ist nicht nötig:

```sh
curl -fsSL https://raw.githubusercontent.com/Tweak81/pi-cc1101-remote/main/install-from-github.sh | bash
```

Der Installer lädt die Projektversion, installiert Abhängigkeiten und
richtet den WLAN-Hotspot ein. Er fragt nach SSID und WLAN-Passwort; Webdienst und
Hotspot starten danach automatisch. Anschließend den Pi neu starten, damit SPI
vollständig aktiviert wird:

```sh
sudo reboot
```

Mit dem iPhone das eingerichtete Pi-WLAN auswählen und `http://10.42.0.1:8080`
öffnen. Die WLAN-Verbindung des Pi zum Heimnetz wird dabei auf `wlan0` durch den
Hotspot ersetzt. Der Pi muss nur während der Installation online sein.

Das Repository ist öffentlich. Quellcode und Git-Historie können von jedem eingesehen
und kopiert werden; persönliche Funksignal-Aufnahmen und Laufzeitdaten sind durch
`.gitignore` vom Repository ausgeschlossen.

### Manuelle Installation aus einem bereits kopierten Ordner

```sh
chmod +x install.sh
./install.sh
./setup-hotspot.sh
sudo reboot
```

Auf aktuellem Raspberry Pi OS (Debian Trixie) ist das frühere `pigpio`-Paket
nicht mehr enthalten. `install.sh` erkennt das automatisch und baut den fehlenden
`pigpiod`-Dienst aus der festgelegten offiziellen Version v79. Auf älteren Systemen
mit vorhandenem Daemon wird dieser Schritt übersprungen. Das kann auf dem Zero 2 W
einige Minuten dauern.

Danach zuerst die Verbindung testen:

```sh
cd pi-cc1101-remote
./rfcontrol.py diagnose
```

Erwartet wird `PARTNUM=0x00` und üblicherweise `VERSION=0x14`.

## Weboberfläche

Die Installation richtet automatisch eine lokale Weboberfläche ein. Im Heim-WLAN nach
dem Neustart im Browser öffnen:

```text
http://raspberrypi.local:8080
```

Falls der Pi einen anderen Rechnernamen hat, dessen IP-Adresse verwenden, zum Beispiel
`http://192.168.1.42:8080`. Die Oberfläche zeigt alle Aufnahmen aus `signals` an.
Jede Karte besitzt einen Senden-Button, eine einstellbare Wiederholungszahl und eine
Option zum Umkehren der Polarität. Neue Signale können oben direkt aufgenommen werden.

Die Seite ist für das vertrauenswürdige Heimnetz vorgesehen und besitzt keine
Benutzeranmeldung. Port 8080 daher nicht im Router ins Internet freigeben.

### Direkter WLAN-Hotspot für das iPhone

Der Installer richtet auf Raspberry Pi OS mit NetworkManager einen eigenen Zugangspunkt
ein. Manuell lässt er sich ebenfalls starten:

```sh
./setup-hotspot.sh
```

Das Skript fragt SSID und Passwort ab und speichert den Hotspot für den automatischen
Start. Es ersetzt die WLAN-Client-Verbindung auf `wlan0`; danach verbindest du das
iPhone mit dem Pi-WLAN und öffnest `http://10.42.0.1:8080`. Währenddessen ist die
bisherige Heim-WLAN-Verbindung über `wlan0` getrennt; Internet bleibt nur verfügbar,
wenn der Pi über eine andere Schnittstelle verbunden ist.

### Empfangsmodi

Oben in der Weboberfläche kann zwischen **Funkfernbedienungen** und **Fahrzeugprotokollen**
gewechselt werden. Fahrzeugprofile sind nach Herstellerfamilie gruppiert. Enthalten sind
Chrysler, Fiat V0/V1/V2, Ford V0/V1/V2/V3, Honda V0/V1/V2 und Static, Kia V0/V1/V2/V3/V4/V5/V6/V7,
Mazda V0, Mitsubishi V0, Peugeot/Citroën, Renault V0/V1, StarLine, Subaru, Suzuki V0 und
VAG (VW/Audi/Seat/Skoda). Die Auswahl setzt die jeweilige Frequenz und Modulation;
insbesondere Ford V2/V3 F4 verwendet **434,25 MHz**, VAG **434,42 MHz AM/OOK**, während
die übrigen hier enthaltenen Standardprofile auf **433,92 MHz** empfangen. Honda Static
Honda1 verwendet **433,65 MHz** und eine eigene CC1101-Konfiguration.

Das sind Protokollfamilien und Empfangsvoreinstellungen, keine bestätigte Liste
kompatibler Fahrzeugmodelle oder Baujahre. Die Auswahl eines Herstellers garantiert
nicht, dass genau dieses Fahrzeug das Profil verwendet. Vor dem Speichern prüft der Pi
jedes Aufnahmefenster anhand der zum Profil gehörenden Decoder-Timings und Mindestlänge.
Er verlangt mindestens zwei wiederholte Rahmen mit passender Pulsstruktur; VAG-Rahmen
müssen zusätzlich mit einer der dokumentierten VAG-Präambeln beginnen. Nicht passende
Funkpulse werden verworfen. Nur der am besten passende Wiederholungscluster wird als
Flipper-RAW-`.sub` unter `vehicle-signals/<profil>` gespeichert. Die Weboberfläche
kennzeichnet diese Daten als wahrscheinlichen Protokolltreffer.

Das ist eine konservative Plausibilitätsprüfung, keine kryptografische Authentifizierung:
ein anderes Funksystem könnte theoretisch dieselbe Timingstruktur senden. Die Pi-Aufnahme
beweist daher nicht, dass der Sender tatsächlich ein bestimmtes Fahrzeug ist. Die
Protokolldekodierung bleibt beim Flipper/ProtoPirate.

Die Profile basieren auf den in ProtoPirate dokumentierten Protokoll-/Frequenzangaben
und den dazu passenden asynchronen CC1101-Voreinstellungen der Flipper-Firmware. Die
Profile mit 315 MHz sind hier nicht auswählbar: Das vorhandene E07-M1101D-Modul ist die
433-MHz-Version und seine Antenne ist für diesen Bereich ausgelegt. Einige in der Tabelle
aufgeführte FM-Varianten Mazda F2?, PSA F3? und Scher-Khan FM haben keine eindeutig
belegten CC1101-Presetwerte in den hier verwendeten Quellen; sie werden daher nicht als
vermeintlich passende Auswahl angeboten.
Vor einem echten Einsatz muss jedes Profil mit dem betreffenden Funksender auf dem Pi
validiert werden. Die Aufnahmen bleiben Rohdaten; dieser Logger versucht keine
Rolling-Code-Entschlüsselung und sendet im Fahrzeugmodus nicht.

Gespeicherte Signale lassen sich in ihrer Karte über **Löschen** entfernen. Eine
Bestätigung verhindert versehentliches Löschen.

## Dauerempfang und Protokollerkennung

Der Dauerempfang wird direkt oben in der Weboberfläche über **Empfang starten** und
**Empfang beenden** gesteuert. Neue unbekannte Signale erscheinen automatisch als
„Fernbedienung 1“, „Fernbedienung 2“ usw. Bereits bekannte Signale erhalten lediglich
einen weiteren Zeitstempel im Ereignislog.

Beim Senden aus der Weboberfläche wird der Dauerempfang beendet, das Signal gesendet
und der Empfang unmittelbar danach automatisch fortgesetzt. Beim manuellen Aufnehmen
verhält es sich ebenso, da der CC1101 nicht gleichzeitig zwei Empfangsarten ausführen
kann. Löschen und Anzeigen unterbrechen den Empfang nicht.

Sendeaktionen laufen im Hintergrund, ohne die Seite neu zu laden. Die aktuelle
Scrollposition bleibt erhalten und eine kurze Statusmeldung bestätigt Erfolg oder Fehler.

### Dauerbetriebsfunktionen

- Der eingeschaltete Dauerempfang wird nach einem Neustart des Pi oder Webdienstes
  automatisch wieder aufgenommen.
- Ein Watchdog prüft alle 30 Sekunden Prozess und Lebenszeichen. Bei einem Absturz oder
  mehr als 150 Sekunden ohne Lebenszeichen wird der Empfänger neu gestartet.
- Der Monitor schreibt im Dauerbetrieb keine Roh-Debugdateien pro Empfangsfenster mehr.
  Das reduziert Schreibzugriffe und Verschleiß der SD-Karte erheblich.
- `events.jsonl` wird bei 5 MB rotiert; eine vorherige Datei bleibt als
  `events.1.jsonl` erhalten. `monitor.log` wird bei 2 MB ebenso rotiert.
- Die Weboberfläche zeigt Laufzeit, letzten Empfang, freien Speicherplatz und Größe des
  Ereignislogs.
- Bei weniger als 100 MB freiem Speicher pausiert der Monitor automatisch, bis wieder
  ausreichend Platz verfügbar ist.

Alternativ kann der Monitor weiterhin im Terminal gestartet werden, etwa für 24 Stunden:

```sh
./monitor.py --hours 24
```

Für unbegrenzten Empfang `--hours 0` verwenden. Das Programm arbeitet in kurzen
Empfangsfenstern. Ein neues Signal wird einmal gespeichert; weitere gleiche Empfänge
werden mit Zeitstempel in `events.jsonl` protokolliert und in der Weboberfläche unter
„Letzte Empfangsereignisse“ angezeigt. Dank einer gemeinsamen Hardwaresperre warten
Senden und manuelle Aufnahmen, bis das aktuelle kurze Empfangsfenster beendet ist.

Der Decoder erkennt derzeit gängige Princeton/PT2262-artige OOK-Festcodes und speichert
Protokoll, Schlüssel, Bitzahl und Grundimpuls `TE`. Nicht sicher erkannte Formate werden
verlustfrei als `RAW` abgelegt. „Button 2“ ist beim Flipper häufig ein frei vergebener
Signalname; aus dem Funktelegramm selbst lassen sich normalerweise Protokoll und Key,
nicht aber die physische Tastenbeschriftung ableiten.

Automatisch erkannte Princeton/EV1527-Signale werden nach der 20-Bit-Gerätekennung
gruppiert, beispielsweise `Princeton52811`. Die letzten vier Bit werden als Befehl
behandelt und – bei der verbreiteten Belegung 1, 2, 4, 8 – als `Taste 1` bis `Taste 4`
angezeigt. Abweichende Befehle bleiben eindeutig als `Taste 0x…` bezeichnet.

Für die Duplikaterkennung wird bei decodierten Signalen der vollständige Schlüssel
verwendet. Derselbe Schlüssel erzeugt nur einen neuen Logeintrag; ein anderer Befehl
bei gleicher Gerätekennung wird als zusätzliche sendbare Taste unter derselben
Fernbedienung gespeichert. Das ist wichtig, weil sich Ein/Aus/Dimmen häufig nur in
wenigen Befehlsbits unterscheiden.

Da die Position der Befehlsbits bei Princeton nicht verbindlich festgelegt ist,
vergleicht der Monitor neue Schlüssel zusätzlich mit bereits bekannten Schlüsseln
desselben Protokolls, derselben Bitzahl und ähnlicher Impulszeit. Unterscheiden sie
sich um höchstens vier Bits, wird die neue Taste der bestehenden Fernbedienung
zugeordnet. Damit funktionieren auch Hersteller, die ihre Tastenbits nicht im letzten
Nibble ablegen.

Zusätzlich werden derzeit die statischen PWM-Formate SMC5326, Nice FLO, Ansonic und
Linear anhand von Bitzahl und Impulszeiten erkannt. Princeton, EV1527 und verschiedene
PT2262-kompatible Sender sind auf der Funkebene teilweise nicht eindeutig unterscheidbar;
die Oberfläche weist deshalb kompatible Protokollfamilien aus. Komplexe Manchester-,
FSK- und Rolling-Code-Protokolle bleiben `RAW` und werden nicht als vermeintlich sicher
erkannte Fernbedienung ausgegeben.

Wiederholte RAW-Muster können beispielsweise von Wetterstationen, Funksensoren oder
Türklingeln stammen. Sie erscheinen als „Unbekanntes RAW-Signal“ im Ereignislog, werden
aber nicht in der Liste der sendbaren Fernbedienungen angelegt. Automatisch sendbar sind
nur die ausdrücklich unterstützten statischen Protokolle Princeton, SMC5326, Nice FLO,
Ansonic und Linear. Manuell aufgenommene RAW-Signale bleiben davon unberührt.

Bereits vorhandene Aufnahmen nachträglich analysieren:

```sh
./rfcontrol.py analyze
```

## Fernbedienung aufnehmen

Fernbedienung zunächst etwa 0,5–2 m von der Antenne entfernt halten:

```sh
./rfcontrol.py record wohnzimmer_an
```

Während der zehn Sekunden dieselbe Taste mindestens fünfmal kurz drücken. Danach:

```sh
./rfcontrol.py list
./rfcontrol.py send wohnzimmer_an
```

Eine erfolgreiche Aufnahme nennt mindestens drei **passende Wiederholungen** und
typischerweise deutlich mehr als 20 Impulse. Erkennt das Programm nur Rauschen,
wird keine sendbare Datei angelegt. Rohkandidaten zur Fehlersuche landen unter
`signals/.debug/NAME.json` und erscheinen nicht in der Weboberfläche.

Während der Aufnahme dient GDO0/GPIO24 als Trägererkennung: Datenflanken von GDO2
werden nur berücksichtigt, wenn der CC1101 ein ausreichend starkes Funksignal
erkennt. Beim Senden wird derselbe GDO0-Pin automatisch zum Dateneingang des CC1101.

Falls die Lampe nicht reagiert:

```sh
./rfcontrol.py send wohnzimmer_an --invert
./rfcontrol.py send wohnzimmer_an --repeats 15
```

Bei einer Aktualisierung des Projekts den vorhandenen Ordner `signals` sichern oder
in den neuen Projektordner übernehmen; dort liegen alle bisherigen Aufnahmen.

Gespeicherte Aufnahmen liegen lesbar als JSON im Ordner `signals`. Nicht während
einer Aufnahme senden. Das Werkzeug ist für eigene Geräte und kurze Tests gedacht;
Frequenz-, Leistungs- und Duty-Cycle-Vorgaben am Einsatzort sind einzuhalten.

## Fehlersuche

- `pigpiod laeuft nicht`: `sudo systemctl start pigpiod`
- `Package pigpio is not available`: die aktuelle Version des Projekts verwenden
  und `./install.sh` erneut starten; das alte `pigpio`-Paket wird nicht mehr angefordert.
- Chipkennung `0xFF`: meist MISO, CSN, Versorgung oder Masse falsch verbunden.
- Keine Impulse: GDO2/Pin 8 prüfen, Abstand variieren und Antenne auf 433 MHz prüfen.
- Sehr viele Störimpulse: Fernbedienung näher heranbringen oder `--gap-us 12000` nutzen.
- Aufnahme klappt, Senden nicht: zuerst `--invert`, danach mehr Wiederholungen testen.

Hinweis: Die Software wurde ohne Zugriff auf die konkrete Lampe erstellt. Der
Hardwaretest und mindestens eine echte Aufnahme auf dem Pi sind daher der nächste
Validierungsschritt.
