# GitHub-Profil einrichten

Dieses Projekt erzeugt drei eigenständige SVGs für **mucsandy**. Das öffentliche
Profil zeigt oben den Beitragskalender und darunter ASCII-Porträt und Infokarte.
Die Details stehen in `profile.json`; mehrere Einträge in einer Zeile werden
automatisch mit dem Mittelpunkt **·** verbunden.

## 1. Als Profil-README verwenden

Dieses Profil ist für das öffentliche Repository
[`mucsandy/mucsandy`](https://github.com/mucsandy/mucsandy) vorbereitet. Die
`README.md`, die drei SVGs und `profile.json` liegen im Stammverzeichnis;
Generatoren und Workflow befinden sich unter `scripts/` beziehungsweise
`.github/workflows/refresh-heatmap.yml`.

Die drei erzeugten SVGs sind bereits direkt einbettbar. Für deren Darstellung
braucht GitHub weder Python noch dein Originalfoto. Für das Profil müssen
Repository-Name und Benutzername übereinstimmen; siehe
[GitHubs Anleitung zum Profil-README](https://docs.github.com/en/account-and-profile/how-tos/profile-customization/managing-your-profile-readme).

Die Automatisierung wird aktiv, sobald ihre Datei auf dem Standardbranch liegt
und GitHub Actions im Repository aktiviert ist. Der erste Push der
Profil-Dateien auf `main` löst die Heatmap-Aktualisierung automatisch aus.
Ein manueller Lauf ist zusätzlich unter
**Actions → Refresh contribution heatmap → Run workflow** möglich.

## 2. Dateien und Zuständigkeiten

| Datei | Aufgabe | Wann neu erzeugen? |
| --- | --- | --- |
| `ascii-portrait.svg` | Monochromes Porträt mit einmaligem zeilenweisen Aufbau | Bei einem neuen Foto oder geänderter Bildabstimmung |
| `info-card.svg` | Persönliche Angaben im Neofetch-Stil | Nach Änderungen an `profile.json` |
| `contrib-heatmap.svg` | Echter öffentlicher 53-Wochen-Kalender mit Statistik | Täglich per Workflow |
| `README.md` | Zentrierte GitHub-kompatible Anordnung | Nach geänderten Abmessungen von Porträt oder Infokarte |
| `data/contributions.json` | Nachprüfbarer normalisierter Datenstand der Heatmap | Gemeinsam mit der Heatmap |
| `scripts/common.py` | Farben, Terminalrahmen, Schriftstack und Animationen | Bei Designänderungen |
| `scripts/validate_svg.py` | XML-, Referenz- und Geometrieprüfung | Nach jeder Änderung an erzeugten SVGs |

Die Originalfotografie bleibt lokal. Lege sie beispielsweise unter
`assets/portrait.jpg` ab. `assets/` und Modell-Caches sind in `.gitignore`
ausgeschlossen; die SVG-Datei enthält ausschließlich Text und SVG-Elemente.

## 3. Lokal starten

Empfohlen ist Python 3.12. Eine virtuelle Umgebung hält die lokalen
Bildverarbeitungs-Abhängigkeiten getrennt:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-art.txt
```

Unter Windows die Aktivierung durch `.venv\Scripts\Activate.ps1` ersetzen.
Die Fotopipeline nutzt `rembg` auf der CPU, OpenCV, Pillow und NumPy. Beim ersten
Aufruf lädt `rembg` das benötigte Segmentierungsmodell; spätere Aufrufe können
den Cache wiederverwenden. Weder Modell noch Foto werden in das SVG eingebettet.

### Foto neu rendern

```bash
python scripts/render_portrait.py --photo assets/portrait.jpg
python scripts/render_readme.py
python scripts/validate_svg.py ascii-portrait.svg info-card.svg contrib-heatmap.svg
```

Die Fotopipeline entfernt zuerst den Hintergrund und bestimmt den Ausschnitt
aus der **Alpha-Silhouette**. Die mediane Breite der oberen Silhouettenzeilen
bestimmt die Kopfgröße; dadurch beeinflussen Schultern den Maßstab weniger.
Haarspitzen bleiben Teil des Ausschnitts, auch wenn sie später sehr dunkel
gerendert werden. Anschließend verstärkt CLAHE den lokalen Kontrast und eine
Tonwertkurve setzt dunkle Bildbereiche auf Schwarz.

Die Zeichenrampe läuft von dunkel nach hell: Ein schwarzer Pixel ergibt ein
Leerzeichen, ein heller Pixel ein dichtes Zeichen. Das Porträt verwendet eine
einzige Zeichenfarbe. Leere Stellen werden nicht als Leerzeichen ausgegeben:
Jeder zusammenhängende Zeichenlauf erhält eine absolute X-Koordinate sowie
`textLength` und `lengthAdjust="spacingAndGlyphs"`. So bleibt das Raster auch
bei einem anderen installierten Monospace-Font stabil.

### Angaben ändern

Bearbeite `profile.json`. Ein einfacher Wert verwendet `value`; eine Reihe von
Punkten verwendet `items`:

```json
{"label": "Focus", "items": ["AI", "LLM Integration"]}
```

Die Ausgabe lautet `AI · LLM Integration`. Ein leeres `label` erzeugt eine
Fortsetzungszeile, wie bei den Sprachkenntnissen. Danach ausführen:

```bash
python scripts/render_info_card.py
```

Dieser Aufruf schreibt die Infokarte und berechnet die README-Bildgrößen neu,
sobald `ascii-portrait.svg` vorhanden ist. Breite und Höhe der Karte passen sich
dem Inhalt und der Anzahl der Zeilen an. Die Infokarte enthält keine
GitHub-Statistiken.

Für eine Gesamtdarstellungsbreite von 850 Pixeln liest `render_readme.py` beide
SVG-`viewBox`-Abmessungen und berechnet:

```text
Porträtbreite = 850 × Porträt-Seitenverhältnis / Summe beider Seitenverhältnisse
Kartenbreite  = 850 × Karten-Seitenverhältnis  / Summe beider Seitenverhältnisse
Gemeinsame Höhe = 850 / Summe beider Seitenverhältnisse
```

Die HTML-Attribute werden auf ganze Pixel gerundet, ihre Breiten summieren sich
weiterhin zu 850. Beide Bilder erhalten dasselbe gerundete Höhenattribut.
GitHubs Bildregeln skalieren sie bei Bedarf proportional; die Rundung lässt
einen Unterschied von weniger als einem Pixel zwischen den Panel-Unterkanten
zu. Die Zellabstände und der Rahmen der GitHub-Tabelle kommen zur Bildbreite
hinzu. Bei weniger Platz verkleinern sich die beiden Bilder gemeinsam.

### Heatmap manuell aktualisieren

Für diesen Weg reichen die zwei kleinen Heatmap-Abhängigkeiten:

```bash
python -m pip install -r requirements.txt
python scripts/fetch_contributions.py --username mucsandy --output data/contributions.json
python scripts/render_heatmap.py --input data/contributions.json --output contrib-heatmap.svg
python scripts/validate_svg.py contrib-heatmap.svg
```

Die Quelle ist ausschließlich die öffentliche HTML-Seite
[`github.com/users/mucsandy/contributions`](https://github.com/users/mucsandy/contributions).
Die Zellen liefern Datum und Farbintensität als `data-date` und `data-level`.
Die genaue Anzahl wird aus einem separaten `tool-tip` gelesen, dessen
`for`-Attribut zur Zellen-ID gehört. Aus einer Intensitätsstufe wird niemals eine
Anzahl geschätzt. Ein verändertes oder unvollständiges HTML-Format führt zu einem
Fehler, damit ein bestehendes korrektes Ergebnis nicht mit erfundenen Daten
überschrieben wird.

Die dargestellte Spanne folgt dem tatsächlich gelesenen Kalender. Wochen laufen
von Sonntag bis Samstag. Nicht zum gelieferten Zeitraum gehörende oder künftige
Tage sind keine gemessenen Nulltage. Die Kennzahlen im Fußbereich beziehen sich
auf den sichtbaren Zeitraum; die Quellen- und Datumsangaben sind im JSON
nachvollziehbar. Eine aktuelle Serie kann den vorherigen Tag einschließen, wenn
der heutige Tag noch keine Beiträge hat. Die konkrete Datums- und
Serienberechnung steht in `scripts/render_heatmap.py`.

## 4. Statische Vorschau

Statische Vorschauen werden lokal unter `previews/` erzeugt. Dieser Ordner ist
durch `.gitignore` vom Profil-Repository ausgeschlossen; die drei animierten
SVGs im Stammverzeichnis bleiben die öffentlich eingebetteten Dateien.

Jeder SVG-Renderer versteht `STATIC=1`. Dann wird direkt der vollständig sichtbare
Endzustand ohne Animation geschrieben. Verwende abweichende Ausgabeziele, um die
animierten Hauptdateien zu behalten:

```bash
mkdir -p previews
STATIC=1 python scripts/render_portrait.py --photo assets/portrait.jpg --output previews/ascii-portrait.svg
STATIC=1 python scripts/render_info_card.py --output previews/info-card.svg
STATIC=1 python scripts/render_heatmap.py --output previews/contrib-heatmap.svg
python scripts/validate_svg.py --static previews/ascii-portrait.svg previews/info-card.svg previews/contrib-heatmap.svg
```

In PowerShell vor dem Aufruf `$env:STATIC="1"` setzen und danach mit
`Remove-Item Env:STATIC` entfernen. Die Haupt-SVGs können danach ohne `STATIC`
erneut erzeugt werden. Sie spielen einmal ab und behalten ihren fertigen Zustand.
Auch Betrachter ohne CSS-Animationen bekommen sichtbare Grundelemente. Die
Animationen respektieren außerdem `prefers-reduced-motion`.

## 5. Täglicher Workflow

Der Workflow ist täglich für **03:17 UTC** vorgesehen: **04:17 Uhr im Münchner
Winter** und **05:17 Uhr im Münchner Sommer**. GitHub kann geplante Läufe
verzögern; die Ausführung hängt vom Standardbranch ab. Diese Eigenschaften und
die automatische Deaktivierung nach längerer Repository-Inaktivität beschreibt
[GitHub unter `schedule`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

Zusätzlich startet er bei Pushes auf `main`, wenn sich der Fetcher,
Heatmap-Renderer, das gemeinsame SVG-Modul, der SVG-Validator,
`requirements.txt`, `profile.json` oder die Workflow-Datei ändern. Damit wird
auch die erste Veröffentlichung geprüft. Reine README-Änderungen und die vom
Bot geschriebenen SVG-/JSON-Dateien lösen diesen Pfadfilter nicht aus.

Er installiert nur `requests` und `beautifulsoup4`, liest den Kalender, rendert
und prüft die Heatmap. In den Commit gelangen ausschließlich
`contrib-heatmap.svg` und `data/contributions.json`. Bei identischem Ergebnis
wird kein Commit erzeugt. Porträt und Infokarte werden im Workflow nicht
angefasst.

Der Workflow übergibt `${{ github.repository_owner }}` als `GH_USER` und liest
den öffentlichen Kalender dieses Accounts. Er enthält daher keinen fest
eingetragenen Benutzernamen. Lokale Aufrufe ohne `--username` verwenden den
Benutzernamen aus `profile.json`; für dieses Profil lautet er `mucsandy`.

Der Kalenderabruf benötigt **keinen Token, kein Secret und keinen Statistikdienst**.
Zum Zurückschreiben des Commits nutzt die Checkout-Action den von GitHub
automatisch bereitgestellten, repositorygebundenen `GITHUB_TOKEN` und
`permissions: contents: write`. Ein persönlicher Access Token ist nicht nötig.
Dieses Verhalten ist im
[offiziellen Checkout-Beispiel](https://github.com/actions/checkout#push-a-commit-using-the-built-in-token)
dokumentiert. Aktuell verwendet der Workflow die offiziellen Actions
`actions/checkout@v7` und `actions/setup-python@v7`.

Die Commit-Nachricht enthält `[skip ci]`. Zusammen mit dem gezielten Pfadfilter
verhindert der Marker, dass gewöhnliche `push`-Workflows durch den Bot-Commit
erneut anlaufen. Siehe
[GitHubs Dokumentation zu Skip-Markern](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/skip-workflow-runs).

## 6. Rendering und Prüfungen

Jedes Panel zeichnet seinen Hintergrund `#0d1117` und den Rand `#21262d` selbst.
Die Darstellung bleibt dadurch in hellem und dunklem GitHub-Design lesbar.
Schriftfamilien kommen aus einem System-Monospace-Stack; es werden keine
Webfonts, externen Stylesheets oder Rasterbilder geladen.

Im öffentlichen README stehen die Bilder ausschließlich in `<img>`-Elementen.
Die untere Zeile verwendet eine zentrierte `<table>` mit `valign="top"` auf
beiden Zellen. Vertikale Abstände verwenden `<br>`, die Überschrift `<h3>`.
Es gibt kein Inline-`style` und keine JavaScript-Abhängigkeit.

Die SVG-Prüfung kontrolliert gültiges XML, verbotene Skripte und externe
Referenzen sowie die numerischen Grenzen der gezeichneten Elemente. Dazu gehören
Textbreiten, Striche, Rechtecke, Kreise und die vollständige Less–More-Legende.
Zusätzlich zu diesen Prüfungen sollten bei Designänderungen die drei statischen
Endzustände und ein frischer Animationsstart im Browser angesehen werden.

Die enthaltenen Regressionstests prüfen insbesondere die Tooltip-Zuordnung,
fehlende Tage, Schaltjahre, Serienberechnung, externe Referenzen und Überläufe:

```bash
python -m unittest discover -s tests -v
```

Die Tonwertabstimmung des Porträts lässt sich über `--black`, `--white`,
`--gamma` und `--head-scale` verändern. Standardwerte sind 52, 218, 1.16 und
1.50. Ein höherer Schwarzpunkt blendet dunkle Kleidung stärker aus. Der
Ausschnitt bleibt dabei weiterhin von der Alpha-Silhouette abhängig. Für
lokale Diagnosebilder kann `--debug-dir .cache/portrait/qa` angegeben werden.
