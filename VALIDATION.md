# Prüfbericht · mucsandy

Prüfstand: 22. Oktober 2026. Das Profil wurde auf `main` veröffentlicht und
der erste gehostete Workflow-Lauf erfolgreich abgeschlossen. Die gelesene
GitHub-Kalenderspanne endet am 22. Oktober 2026 in UTC. Es wurden keine Tage
oder Beiträge ergänzt, die nicht in der öffentlichen Quelle vorhanden sind.

## Erzeugte Panels

| Datei | SVG-Abmessungen | Ende der einmaligen Animation |
| --- | --- | --- |
| `ascii-portrait.svg` | 440 × 580 | 2,796 s |
| `info-card.svg` | 620 × 479 | 1,605 s |
| `contrib-heatmap.svg` | 1060 × 350 | 1,980 s |

Die unteren README-Bilder sind aus diesen Seitenverhältnissen berechnet:
314 + 536 = 850 Pixel. Beide bekommen das gerundete Höhenattribut 414 Pixel.
Die Heatmap wird darüber mit 850 Pixeln Breite eingebettet.

## Tatsächlich gelesene Beiträge

Quelle: <https://github.com/users/mucsandy/contributions>, ohne Authentifizierung.
Der gespeicherte Datenstand steht in `data/contributions.json`. Die folgenden
Werte beschreiben den Snapshot des ersten automatischen Laufs; spätere tägliche
Aktualisierungen können davon abweichen.

| Eigenschaft | Wert |
| --- | --- |
| Beobachteter Zeitraum | 2025-10-19 bis 2026-10-22, UTC |
| Beobachtete Tage | 369 |
| Wochenspalten | 53, Sonntag zuerst |
| Kommende Randzellen | 2, nur als Umriss und ohne erfundene Anzahl |
| Beiträge im Zeitraum | 10 |
| Aktive Tage | 3 |
| Längste Serie im Zeitraum | 2 Tage |
| Aktuelle Serie am letzten Quelldatum | 2 Tage |

Die Tage mit Beiträgen sind 2026-02-13 mit 7, 2026-10-21 mit 1 und
2026-10-22 mit 2.
Die Summe aller über IDs zugeordneten Tooltips stimmt mit GitHubs Gesamtzahl
überein. Die Farbintensitäten wurden separat aus `data-level` übernommen.

## Automatisierte Prüfungen

**32 Regressionstests bestanden.** Sie prüfen unter anderem:

- Tooltip-Zuordnung nach ID statt Reihenfolge und exakte Anzahl statt Farbstufe.
- Fehlende oder doppelte Tage, fehlende Tooltips, ungültige Levels und
  widersprüchliche Gesamtzahlen.
- Sonntagsspalten, Jahreswechsel, Schaltjahr, unbekannte Randtage und Serien.
- Fehlerhaftes XML, Skripte, Eventhandler, externe Referenzen und Webfonts.
- Überlaufende Legenden, Strichbreiten und die Endpunkte animierter Geometrie.
- Unerlaubte Leerzeichen in ASCII-Zeichenläufen und wiederholte Animationen.

Alle drei animierten SVGs und alle drei `STATIC=1`-Endzustände bestehen die
XML-, Ressourcen- und Begrenzungsprüfung. Die statischen SVGs enthalten keine
Animationen. Das Porträt besteht aus absolut positionierten, einfarbigen
Zeichenläufen mit expliziter Textlänge; kein Zeichenlauf enthält Leerzeichen.

Die Heatmap-Legende endet bei x = 1036 in einem 1060 Pixel breiten Panel:
**24 Pixel rechter Abstand**. Das Kalenderraster endet bei x = 1026:
**34 Pixel rechter Abstand**. Der bewusst bis zum Panelrand reichende
Rahmen ist einschließlich seines ein Pixel breiten Strichs innerhalb der
SVG-Grenzen.

## Prüfung im echten Browser

Die Browserprüfungen erfolgten vor der Veröffentlichung mit dem Kalenderstand
vom 21. Oktober. Der erste automatische Lauf hat anschließend nur die
Kalenderdaten und die daraus erzeugte Heatmap aktualisiert und deren XML,
Ressourcen und Geometrie erneut geprüft.

Chromium 134.0.6998.35 hat die tatsächlichen `getBBox()`-Grenzen einschließlich
Strichbreiten geprüft: 137 sichtbare Zeichenelemente im Porträt, 32 in der Karte
und 415 in der Heatmap. **Kein Element überschreitet das jeweilige Panel.**
Die zusätzlichen 50 Porträt-Clipping-Rechtecke wurden außerdem durch den
numerischen SVG-Validator geprüft.

Die Animationen wurden bei 0, 600, 1500, 4000 und 6000 Millisekunden geprüft.
Anfang und Endzustand unterscheiden sich. Die Bilder nach 4000 und 6000
Millisekunden sind jeweils identisch: Der Endzustand bleibt stehen.

Bei direkt geöffneten SVGs zeigt `prefers-reduced-motion: reduce` den fertigen
Inhalt sofort und deaktiviert alle Animationen. Unterschiede in der
Kantenglättung von Text zwischen animiertem und unbewegtem Rendering verändern
weder Inhalt noch Abmessungen. Verwendet wurde der installierte Systemfont
DejaVu Sans Mono; es wurde kein Webfont geladen.

Zusätzlich wurden die unveränderten animierten Dateien als echte `<img>`-Bilder
in eine HTML-Seite eingebettet. Sie bauen sich sichtbar auf; die Endzustände
nach vier und fünf Sekunden sind bytegleich. Die undurchsichtigen Panel-Inhalte
sind auf weißem und dunklem Seitenhintergrund ebenfalls bytegleich. Damit wurde
die für ein README relevante Einbettung ausdrücklich mitgeprüft.

## Integration in das Profil-Repository

GitHubs öffentliche Markdown-API hat die endgültige `README.md` mit dem Kontext
`mucsandy/mucsandy` verarbeitet. Die `<h3>`-Überschriften, zentrierte Tabelle,
`valign="top"`, Bildabmessungen und relativen Footer-Links bleiben erhalten.
Alle verlinkten Dateien und Verzeichnisse sind im Repository vorhanden.

Die Ausgabe wurde zusätzlich mit GitHubs aktuellen Stylesheets in Chromium
geprüft. Die Überschriften haben keine Unterstreichung, und die beiden unteren
Panels beginnen an derselben Y-Koordinate. GitHub ergänzt bei Bildern selbst
`height: auto`; das Höhenattribut wird zu einer maximalen Höhe. Bei 850 Pixeln
Inhaltsbreite beträgt der Unterschied der unteren Panelkanten deshalb rund
0,20 Pixel durch die gerundeten Breiten. Die Tabelle passt sich ohne horizontalen
Überlauf an Inhaltsbreiten von 950, 850, 720 und 360 Pixeln an.

GitHubs Zellabstände und Tabellenrahmen benötigen zusätzlich insgesamt
55 Pixel. Bei ausreichend Platz sind die beiden Bilder zusammen 850 Pixel
breit und die Tabelle 905 Pixel. Bei schmaleren Inhaltsbereichen werden beide
Bilder proportional verkleinert. Die README-Datei enthält keine eigenen
Inline-Styles, die GitHubs Sanitizer entfernen könnte.

## Workflow und Repository

Der tägliche Workflow installiert ausschließlich die beiden expliziten
Abhängigkeiten `requests` und `beautifulsoup4`. Er lädt öffentliche HTML-Daten,
erzeugt und prüft die Heatmap und übernimmt nur die SVG-Datei und die
normalisierte JSON-Datei in einen Commit mit `[skip ci]`.

`permissions: contents: write` ist gesetzt. Der Datenabruf enthält keinen
Token. Die Checkout-Action verwendet für das Zurückschreiben des Commits
GitHubs automatisch bereitgestellte Repository-Berechtigung; ein persönlicher
Access Token oder ein zusätzliches Secret ist nicht erforderlich.

Der Workflow reagiert außerdem auf den ersten Push sowie relevante Änderungen
an Generatoren, Konfiguration und Workflow auf `main`. Er liest den Account
aus `github.repository_owner`. Die YAML-Struktur und alle Shell-Schritte wurden
lokal geprüft; Fetch, Rendering und SVG-Validierung wurden erfolgreich ausgeführt.

Das Repository enthält Quellcode, Konfiguration, Workflow und die drei
animierten SVGs. Statische Vorschauen werden bei Bedarf lokal erzeugt.
Originalfoto, Freistellungsbilder, Modellgewichte, virtuelle Umgebungen und
Browser-Prüfbilder gehören nicht zum Repository.

## Erneut prüfen

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/validate_svg.py
```

Die Befehle zum Erzeugen und Prüfen statischer Vorschauen stehen in
[`SETUP.md`](SETUP.md#4-statische-vorschau).

## Veröffentlichung und erster GitHub-Lauf

Das öffentliche [Profil](https://github.com/mucsandy) und das
[Repository](https://github.com/mucsandy/mucsandy) liefern das fertige README.
Die drei tatsächlich im Profil eingebetteten Bild-URLs wurden abgerufen:
alle liefern HTTP 200, `image/svg+xml` und gültiges SVG-XML. Überschriften,
zentrierte Tabelle, `valign="top"`, Bildmaße und Footer-Links sind auch im
ausgelieferten Profil-HTML vorhanden.

Die Veröffentlichung erfolgte mit
[Commit `856a769`](https://github.com/mucsandy/mucsandy/commit/856a769d25b46f7ad250717e613313a264055fc0).
Der Dateibaum auf GitHub stimmt exakt mit dem zuvor geprüften lokalen Dateibaum
überein.

[Workflow-Lauf #1](https://github.com/mucsandy/mucsandy/actions/runs/39697379030)
wurde durch diesen Push gestartet und am 22. Oktober 2026 um 00:04 UTC mit
`success` abgeschlossen. Checkout, Python-Setup, Installation der beiden
Abhängigkeiten, öffentlicher Datenabruf, Rendering, SVG-Validierung und
automatischer Commit waren erfolgreich.

Der Bot hat mit
[Commit `4ee8572`](https://github.com/mucsandy/mucsandy/commit/4ee8572)
ausschließlich `contrib-heatmap.svg` und `data/contributions.json` aktualisiert.
Die Nachricht enthält `[skip ci]`. Damit ist auch das Zurückschreiben in das
Repository praktisch bestätigt. Der tägliche Zeitplan bleibt auf 03:17 UTC.
