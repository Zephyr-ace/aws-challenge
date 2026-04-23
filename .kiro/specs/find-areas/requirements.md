# Anforderungsdokument: find-areas

## Einleitung

Die Funktion `find_areas` identifiziert potenzielle Grundstücke für Rechenzentren in Deutschland. Sie durchsucht Industriegebiete über die OpenStreetMap Overpass API, nutzt einen KI-gestützten Web-Research-Agenten zur Informationsanreicherung (Name, Verkaufsstatus, Grundstücksgrößen) und filtert die Ergebnisse optional nach Nähe zu Hochspannungsleitungen und Wasserquellen. Die Filterkriterien sind über eine Konfigurationsdatei aktivierbar und konfigurierbar.

## Glossar

- **Find_Areas_Pipeline**: Die Hauptfunktion `find_areas`, die den gesamten Ablauf orchestriert – von der Konfiguration über die Datenabfrage bis zur gefilterten Ergebnisliste.
- **Config_Loader**: Komponente, die die YAML/JSON-Konfigurationsdatei liest, validiert und als `AppConfig`-Objekt bereitstellt.
- **AppConfig**: Datenstruktur, die die gesamte Konfiguration enthält (Filter-Einstellungen und LLM-Einstellungen).
- **FilterConfig**: Datenstruktur mit den Filterkriterien (Kriterium B und C) und deren Schwellwerten.
- **LLMConfig**: Datenstruktur mit den LLM-Verbindungsparametern (base_url, api_key, model).
- **LLM_Helper**: Generischer Wrapper um die OpenAI Chat Completions API, der Chat-Anfragen und Tool-Use-Schleifen verwaltet.
- **Web_Research_Agent**: Komponente, die den LLM_Helper und eine Websuch-API nutzt, um Informationen über Industriegebiete zu recherchieren.
- **WebResearchResult**: Datenstruktur mit den Ergebnissen der Web-Recherche (Name, Verkaufsstatus, Grundstücksgrößen, Konfidenz, Quellen).
- **Overpass_Client**: Komponente, die mit der OpenStreetMap Overpass API kommuniziert und Geodaten abruft.
- **Filter_Engine**: Komponente, die Industriegebiete anhand aktiver Distanzkriterien filtert.
- **Metadaten_Enricher**: Komponente, die gefilterte Grundstücke mit zusätzlichen Metadaten anreichert (Distanzen, Namen).
- **AreaResult**: Rückgabeformat der Pipeline – ein Dictionary mit Standortdaten, Grundstücksgröße und Metadaten.
- **Kriterium_B**: Filterkriterium für Nähe zu Hochspannungsleitungen (konfigurierbar, Standard: < 20 km).
- **Kriterium_C**: Filterkriterium für Nähe zu Wasserquellen (konfigurierbar, Standard: < 1 km).
- **Haversine_Distanz**: Berechnung der Großkreisdistanz zwischen zwei Punkten auf der Erdoberfläche.
- **Punkt_zu_Polyline_Distanz**: Minimale Distanz von einem Punkt zu einer Polyline (Linienzug), berechnet über Projektion auf einzelne Segmente.

## Anforderungen

### Anforderung 1: Konfiguration laden und validieren

**User Story:** Als Entwickler möchte ich die Pipeline über eine Konfigurationsdatei steuern, damit ich Filterkriterien und LLM-Einstellungen flexibel anpassen kann.

#### Akzeptanzkriterien

1. WHEN eine gültige Konfigurationsdatei übergeben wird, THE Config_Loader SHALL die Datei lesen und ein AppConfig-Objekt mit FilterConfig und LLMConfig zurückgeben.
2. WHEN Parameter in der Konfigurationsdatei fehlen, THE Config_Loader SHALL Standardwerte setzen (proximity_power_line_enabled=False, proximity_water_source_enabled=False, max_distance_power_line_km=20.0, max_distance_water_source_km=1.0).
3. IF die Konfigurationsdatei nicht existiert oder ungültige Werte enthält, THEN THE Config_Loader SHALL einen ConfigError mit einer Beschreibung des Problems auslösen.
4. THE Config_Loader SHALL validieren, dass max_distance_power_line_km und max_distance_water_source_km größer als 0 sind.
5. THE Config_Loader SHALL validieren, dass llm.base_url eine gültige URL ist und llm.model nicht leer ist.
6. THE Config_Loader SHALL Umgebungsvariablen in der Konfigurationsdatei auflösen (z.B. `${OPENAI_API_KEY}`).

### Anforderung 2: Industriegebiete aus OpenStreetMap abfragen

**User Story:** Als Entwickler möchte ich alle Industriegebiete in Deutschland aus OpenStreetMap abrufen, damit ich potenzielle Rechenzentrum-Standorte identifizieren kann.

#### Akzeptanzkriterien

1. WHEN die Pipeline gestartet wird, THE Overpass_Client SHALL alle Industriegebiete in Deutschland abfragen (landuse=industrial, way und relation).
2. THE Overpass_Client SHALL für jedes Industriegebiet die Zentrumskoordinaten (lat, lon) und vorhandene Tags zurückgeben.
3. WHEN die Overpass API nicht innerhalb von 180 Sekunden antwortet, THE Overpass_Client SHALL einen OverpassTimeoutError auslösen.
4. IF ein Netzwerkfehler auftritt, THEN THE Overpass_Client SHALL einen ConnectionError auslösen.
5. WHEN die Overpass-Abfrage keine Ergebnisse liefert, THE Overpass_Client SHALL eine leere Liste zurückgeben.

### Anforderung 3: Web-Research für Industriegebiete durchführen

**User Story:** Als Entwickler möchte ich für jedes Industriegebiet per Web-Recherche den Namen, verfügbare Grundstücke und deren Größen ermitteln, damit die Ergebnisse über OSM-Daten hinaus angereichert werden.

#### Akzeptanzkriterien

1. THE Web_Research_Agent SHALL für jedes Industriegebiet anhand von Koordinaten und optionalen OSM-Tags eine LLM-gesteuerte Websuche durchführen.
2. WHEN die Web-Recherche abgeschlossen ist, THE Web_Research_Agent SHALL ein WebResearchResult mit area_name, has_plots_for_sale, plot_sizes_sqm, confidence und sources zurückgeben.
3. THE Web_Research_Agent SHALL über den LLM_Helper geeignete Suchanfragen erstellen und die Suchergebnisse durch das LLM analysieren lassen.
4. THE LLM_Helper SHALL die Tool-Use-Schleife maximal 5 Iterationen ausführen (Anfrage → Tool-Call → Ausführung → Antwort).
5. IF die Websuche oder LLM-Analyse keine verwertbaren Informationen liefert, THEN THE Web_Research_Agent SHALL ein WebResearchResult mit Standardwerten zurückgeben (area_name=None, has_plots_for_sale=False, confidence=0.0).
6. IF die Websuch-API einen Fehler zurückgibt, THEN THE Web_Research_Agent SHALL den Fehler loggen und die Recherche für dieses Gebiet mit Standardwerten abschließen.
7. IF die OpenAI API einen Fehler zurückgibt (Rate Limit, ungültiger API-Key), THEN THE LLM_Helper SHALL einen LLMError mit HTTP-Statuscode und Fehlermeldung auslösen.
8. THE WebResearchResult SHALL einen confidence-Wert im Bereich 0.0 bis 1.0 enthalten.

### Anforderung 4: Hochspannungsleitungen abfragen und Distanz berechnen

**User Story:** Als Entwickler möchte ich Hochspannungsleitungen aus OpenStreetMap abrufen und die Distanz zu Industriegebieten berechnen, damit ich nach Nähe zu Strominfrastruktur filtern kann.

#### Akzeptanzkriterien

1. WHERE Kriterium_B aktiviert ist, THE Overpass_Client SHALL alle Hochspannungsleitungen in Deutschland abfragen (power=line, voltage 110kV/220kV/380kV) mit vollständiger Geometrie (out geom).
2. WHERE Kriterium_B aktiviert ist, THE Filter_Engine SHALL die minimale Punkt_zu_Polyline_Distanz vom Industriegebiet-Zentrum zur nächsten Hochspannungsleitung berechnen.
3. THE Filter_Engine SHALL für die Punkt_zu_Polyline_Distanz eine Equirectangular-Projektion verwenden und den Projektionspunkt auf das Segment [A, B] klemmen.
4. THE Filter_Engine SHALL einen cKDTree-Index über alle Knoten aller Hochspannungsleitungen erstellen, um die Suche effizient durchzuführen.
5. WHERE Kriterium_B aktiviert ist, THE Filter_Engine SHALL nur Industriegebiete behalten, deren minimale Distanz zur nächsten Hochspannungsleitung kleiner als der konfigurierte Schwellwert ist.

### Anforderung 5: Wasserquellen abfragen und Distanz berechnen

**User Story:** Als Entwickler möchte ich Wasserquellen aus OpenStreetMap abrufen und die Distanz zu Industriegebieten berechnen, damit ich nach Nähe zu Wasserinfrastruktur filtern kann.

#### Akzeptanzkriterien

1. WHERE Kriterium_C aktiviert ist, THE Overpass_Client SHALL alle Wasserquellen in Deutschland abfragen (waterway: river/canal, natural=water) mit Mittelpunkt und Tags (out center tags).
2. WHERE Kriterium_C aktiviert ist, THE Filter_Engine SHALL die Haversine_Distanz vom Industriegebiet-Zentrum zum nächsten Wasserquellen-Mittelpunkt berechnen.
3. WHERE Kriterium_C aktiviert ist, THE Filter_Engine SHALL nur Industriegebiete behalten, deren minimale Distanz zur nächsten Wasserquelle kleiner als der konfigurierte Schwellwert ist.

### Anforderung 6: Filterkriterien anwenden

**User Story:** Als Entwickler möchte ich Industriegebiete nach konfigurierbaren Distanzkriterien filtern, damit nur geeignete Standorte in der Ergebnisliste erscheinen.

#### Akzeptanzkriterien

1. THE Filter_Engine SHALL nur die in der Konfiguration aktivierten Kriterien anwenden.
2. WHILE Kriterium_B deaktiviert ist, THE Filter_Engine SHALL keine Filterung nach Hochspannungsleitungen durchführen und kein distance_power_line_km-Feld im Ergebnis enthalten.
3. WHILE Kriterium_C deaktiviert ist, THE Filter_Engine SHALL keine Filterung nach Wasserquellen durchführen und kein water_source_name-Feld im Ergebnis enthalten.
4. THE Filter_Engine SHALL eine Ergebnisliste zurückgeben, die nie größer ist als die Eingabeliste der Industriegebiete.

### Anforderung 7: Metadaten anreichern

**User Story:** Als Entwickler möchte ich die gefilterten Grundstücke mit zusätzlichen Metadaten anreichern, damit die Ergebnisse alle relevanten Informationen für eine Standortbewertung enthalten.

#### Akzeptanzkriterien

1. THE Metadaten_Enricher SHALL für jedes gefilterte Grundstück ein AreaResult mit latitude, longitude, area_sqm, industrial_area_name, has_plots_for_sale, plot_sizes_sqm, research_confidence und research_sources erstellen.
2. WHERE Kriterium_B aktiviert ist, THE Metadaten_Enricher SHALL die Distanz zur nächsten Hochspannungsleitung als distance_power_line_km im AreaResult einfügen.
3. WHERE Kriterium_C aktiviert ist, THE Metadaten_Enricher SHALL den Namen und die Distanz zur nächsten Wasserquelle als water_source_name und distance_water_source_km im AreaResult einfügen.

### Anforderung 8: Distanzberechnung

**User Story:** Als Entwickler möchte ich korrekte Distanzberechnungen zwischen Koordinaten durchführen, damit die Filterung zuverlässige Ergebnisse liefert.

#### Akzeptanzkriterien

1. THE Filter_Engine SHALL die Haversine-Formel für Punkt-zu-Punkt-Distanzberechnungen verwenden.
2. THE Filter_Engine SHALL für Punkt-zu-Polyline-Distanzberechnungen die orthogonale Projektion auf jedes Segment der Polyline berechnen und den minimalen Wert zurückgeben.
3. THE Haversine_Distanz SHALL symmetrisch sein: haversine(A, B) ist gleich haversine(B, A).
4. THE Haversine_Distanz SHALL immer einen Wert größer oder gleich 0 zurückgeben.
5. THE Punkt_zu_Polyline_Distanz SHALL immer kleiner oder gleich der Distanz zu beiden Endpunkten des Segments sein.

### Anforderung 9: Gesamtpipeline

**User Story:** Als Entwickler möchte ich die gesamte Pipeline mit einem einzigen Funktionsaufruf starten, damit der Ablauf einfach und konsistent ist.

#### Akzeptanzkriterien

1. WHEN find_areas mit einem Konfigurationspfad aufgerufen wird, THE Find_Areas_Pipeline SHALL die Schritte Konfiguration laden, Industriegebiete abfragen, Web-Research durchführen, optional filtern und Metadaten anreichern in dieser Reihenfolge ausführen.
2. THE Find_Areas_Pipeline SHALL eine Liste von AreaResult-Dictionaries zurückgeben.
3. THE Find_Areas_Pipeline SHALL für jedes AreaResult gültige Koordinaten enthalten (Latitude: -90 bis 90, Longitude: -180 bis 180).

### Anforderung 10: LLM Helper

**User Story:** Als Entwickler möchte ich einen generischen LLM-Wrapper nutzen, damit verschiedene Komponenten die OpenAI Chat Completions API einheitlich verwenden können.

#### Akzeptanzkriterien

1. THE LLM_Helper SHALL den OpenAI-Client mit konfigurierbarer base_url, api_key und model initialisieren.
2. THE LLM_Helper SHALL Chat-Anfragen mit und ohne Tool-Definitionen an die OpenAI API senden.
3. WHEN das LLM einen Tool-Call zurückgibt, THE LLM_Helper SHALL den Tool-Call über den übergebenen tool_executor ausführen und das Ergebnis zurück an das LLM senden.
4. IF die maximale Anzahl an Tool-Call-Iterationen erreicht ist, THEN THE LLM_Helper SHALL die Schleife beenden und die letzte verfügbare Antwort zurückgeben.
5. IF ein transienter API-Fehler auftritt (z.B. Rate Limit), THEN THE LLM_Helper SHALL eine Retry-Logik mit exponentiellem Backoff anwenden.
