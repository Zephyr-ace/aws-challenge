# Implementierungsplan: find-areas

## Übersicht

Schrittweise Implementierung der `find_areas`-Pipeline in Python. Die Aufgaben bauen aufeinander auf: Zuerst Datenmodelle und Konfiguration, dann die einzelnen Komponenten (Overpass-Client, LLM Helper, Web-Research-Agent, Filter-Engine, Metadaten-Anreicherung), und abschließend die Pipeline-Integration.

## Aufgaben

- [x] 1. Projektstruktur und Datenmodelle anlegen
  - [x] 1.1 Projektstruktur erstellen und Abhängigkeiten definieren
    - Verzeichnisstruktur anlegen (z.B. `find_areas/`, `tests/`)
    - `requirements.txt` oder `pyproject.toml` mit Abhängigkeiten erstellen: `requests`, `openai`, `PyYAML`, `numpy`, `scipy`, `hypothesis`
    - _Anforderungen: 9.1_

  - [x] 1.2 Datenmodelle implementieren
    - `LLMConfig`, `FilterConfig`, `AppConfig` als Dataclasses erstellen
    - `WebResearchResult` als Dataclass erstellen (mit `field(default_factory=...)` für Listen)
    - `AreaResult` als TypedDict mit `NotRequired`-Feldern erstellen
    - Benutzerdefinierte Exceptions erstellen: `ConfigError`, `OverpassTimeoutError`, `LLMError`
    - _Anforderungen: 1.1, 1.2, 3.2, 7.1_

- [x] 2. Config-Loader implementieren
  - [x] 2.1 Config-Loader mit Validierung implementieren
    - `load_config(config_path: str) -> AppConfig` implementieren
    - YAML/JSON-Datei lesen und parsen
    - Standardwerte setzen für fehlende Parameter (`proximity_power_line_enabled=False`, `proximity_water_source_enabled=False`, `max_distance_power_line_km=20.0`, `max_distance_water_source_km=1.0`)
    - Validierung: `max_distance_power_line_km > 0`, `max_distance_water_source_km > 0`
    - Validierung: `llm.base_url` ist gültige URL, `llm.model` nicht leer
    - Umgebungsvariablen auflösen (z.B. `${OPENAI_API_KEY}`)
    - `ConfigError` bei ungültiger Datei oder ungültigen Werten auslösen
    - _Anforderungen: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 2.2 Property-Test: Konfiguration Round-Trip mit Standardwerten
    - **Property 1: Konfiguration Round-Trip mit Standardwerten**
    - Für jede gültige Konfigurationsdatei (auch mit fehlenden optionalen Parametern) soll das Laden ein AppConfig-Objekt erzeugen, bei dem alle explizit gesetzten Werte erhalten bleiben und fehlende Parameter korrekte Standardwerte erhalten.
    - **Validiert: Anforderungen 1.1, 1.2**

  - [ ]* 2.3 Property-Test: Ungültige Konfiguration wird abgelehnt
    - **Property 2: Ungültige Konfiguration wird abgelehnt**
    - Für jede Konfigurationsdatei mit ungültigen Werten (max_distance <= 0, ungültige base_url, leerer model-String) soll der Config_Loader einen ConfigError auslösen.
    - **Validiert: Anforderungen 1.3, 1.4, 1.5**

  - [ ]* 2.4 Unit-Tests für Config-Loader
    - Testen mit gültiger Konfigurationsdatei
    - Testen mit fehlenden optionalen Parametern (Standardwerte prüfen)
    - Testen mit nicht existierender Datei (ConfigError)
    - Testen mit ungültigen Werten (ConfigError)
    - Testen der Umgebungsvariablen-Auflösung
    - _Anforderungen: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 3. Distanzberechnungen implementieren
  - [x] 3.1 Haversine-Distanzberechnung implementieren
    - `haversine(lat1, lon1, lat2, lon2) -> float` implementieren
    - Erdradius: 6371.0 km
    - _Anforderungen: 8.1, 8.3, 8.4_

  - [x] 3.2 Punkt-zu-Segment-Distanzberechnung implementieren
    - `point_to_segment_distance_km(px, py, ax, ay, bx, by) -> float` implementieren
    - Equirectangular-Projektion für lokale Koordinatenumrechnung
    - Projektionspunkt auf Segment [A, B] klemmen (t ∈ [0, 1])
    - Zurückkonvertierung in lat/lon und Haversine-Distanz berechnen
    - _Anforderungen: 8.2, 8.5_

  - [x] 3.3 Polyline-Distanzberechnung implementieren
    - `min_distance_to_power_line(area_lat, area_lon, geometry) -> float` implementieren
    - Über alle Segmente der Polyline iterieren und minimale Distanz zurückgeben
    - _Anforderungen: 4.2, 8.2_

  - [ ]* 3.4 Property-Test: Haversine-Distanz ist symmetrisch und nicht-negativ
    - **Property 11: Haversine-Distanz ist symmetrisch und nicht-negativ**
    - Für alle Koordinatenpaare (A, B): haversine(A, B) == haversine(B, A) und haversine(A, B) >= 0.
    - **Validiert: Anforderungen 8.3, 8.4**

  - [ ]* 3.5 Property-Test: Punkt-zu-Segment-Distanz ist minimal
    - **Property 12: Punkt-zu-Segment-Distanz ist minimal**
    - Für jeden Punkt P und jedes Segment [A, B]: Punkt-zu-Segment-Distanz <= Distanz zu A und <= Distanz zu B.
    - **Validiert: Anforderung 8.5**

  - [ ]* 3.6 Unit-Tests für Distanzberechnungen
    - Testen mit bekannten Koordinatenpaaren (z.B. Berlin → München)
    - Testen von Punkt auf Segment, Punkt am Endpunkt, Punkt senkrecht zum Segment
    - Testen mit degeneriertem Segment (A == B)
    - _Anforderungen: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 4. Checkpoint – Basis-Komponenten prüfen
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer konsultieren.

- [x] 5. Overpass-Client implementieren
  - [x] 5.1 Overpass-Client für Industriegebiete implementieren
    - `OverpassClient` Klasse erstellen
    - `query_industrial_areas() -> list[dict]` implementieren
    - Overpass-Query: `landuse=industrial`, `way` und `relation`, `area["ISO3166-1"="DE"]`, `out center tags`
    - Timeout: 180 Sekunden
    - JSON-Antwort parsen: Zentrumskoordinaten und Tags extrahieren
    - `OverpassTimeoutError` bei Timeout, `ConnectionError` bei Netzwerkfehler
    - Leere Liste bei keinen Ergebnissen zurückgeben
    - _Anforderungen: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 5.2 Overpass-Client für Hochspannungsleitungen implementieren
    - `query_power_lines() -> list[dict]` implementieren
    - Overpass-Query: `power=line`, `voltage~"110000|220000|380000"`, `out geom`
    - Vollständige Geometrie (alle Knoten) abrufen
    - _Anforderungen: 4.1_

  - [x] 5.3 Overpass-Client für Wasserquellen implementieren
    - `query_water_sources() -> list[dict]` implementieren
    - Overpass-Query: `waterway~"river|canal"`, `natural=water`, `out center tags`
    - Mittelpunkte und Namen abrufen
    - _Anforderungen: 5.1_

  - [ ]* 5.4 Property-Test: Overpass-Antwort-Parsing liefert Koordinaten und Tags
    - **Property 3: Overpass-Antwort-Parsing liefert Koordinaten und Tags**
    - Für jede gültige Overpass-JSON-Antwort soll der Parser für jedes Element die Zentrumskoordinaten (lat, lon) und die vorhandenen Tags extrahieren.
    - **Validiert: Anforderung 2.2**

  - [ ]* 5.5 Unit-Tests für Overpass-Client
    - Testen mit gemockter Overpass API (gültige Antwort, leere Antwort, Timeout, Netzwerkfehler)
    - Testen des JSON-Parsings für alle drei Query-Typen
    - _Anforderungen: 2.1, 2.2, 2.3, 2.4, 2.5, 4.1, 5.1_

- [x] 6. LLM Helper implementieren
  - [x] 6.1 LLM Helper Klasse implementieren
    - `LLMHelper` Klasse erstellen mit konfigurierbarer `base_url`, `api_key`, `model`
    - `chat()` Methode: Chat Completions API aufrufen (mit und ohne Tools)
    - `chat_with_tools()` Methode: Tool-Use-Schleife implementieren (max_iterations=5)
    - Retry-Logik mit exponentiellem Backoff bei transienten API-Fehlern
    - `LLMError` bei API-Fehlern (Rate Limit, ungültiger API-Key) auslösen
    - _Anforderungen: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 6.2 Property-Test: Tool-Use-Schleife terminiert
    - **Property 5: Tool-Use-Schleife terminiert**
    - Für jede Sequenz von LLM-Antworten (auch endlose Tool-Calls) soll die Schleife nach maximal max_iterations Zyklen terminieren.
    - **Validiert: Anforderungen 3.4, 10.4**

  - [ ]* 6.3 Unit-Tests für LLM Helper
    - Testen mit gemockter OpenAI API
    - Testen der Tool-Use-Schleife (1 Iteration, max Iterationen, finale Textantwort)
    - Testen der Fehlerbehandlung (Rate Limit, ungültiger API-Key)
    - Testen der Retry-Logik
    - _Anforderungen: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 7. Web-Research-Agent implementieren
  - [x] 7.1 Web-Research-Agent Klasse implementieren
    - `WebResearchAgent` Klasse erstellen mit `LLMHelper` und optionalem Websuch-API-Key
    - `research_area(lat, lon, osm_tags) -> WebResearchResult` implementieren
    - System-Prompt erstellen für LLM-gesteuerte Websuche
    - Websuch-Tool als OpenAI Function Call definieren
    - LLM-Antwort in `WebResearchResult` parsen
    - Graceful Degradation: Bei Fehlern Standardwerte zurückgeben (area_name=None, has_plots_for_sale=False, confidence=0.0)
    - Websuch-API-Fehler loggen und mit Standardwerten abschließen
    - _Anforderungen: 3.1, 3.2, 3.3, 3.5, 3.6_

  - [ ]* 7.2 Property-Test: WebResearchResult ist immer gültig
    - **Property 4: WebResearchResult ist immer gültig**
    - Für jede Web-Recherche soll das WebResearchResult einen confidence-Wert im Bereich [0.0, 1.0] enthalten und alle Pflichtfelder besitzen.
    - **Validiert: Anforderungen 3.2, 3.8**

  - [ ]* 7.3 Unit-Tests für Web-Research-Agent
    - Testen mit gemocktem LLM Helper und gemockter Websuch-API
    - Testen des Parsings der LLM-Antworten
    - Testen der Graceful Degradation bei Fehlern
    - _Anforderungen: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7_

- [x] 8. Checkpoint – Kernkomponenten prüfen
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer konsultieren.

- [x] 9. Filter-Engine implementieren
  - [x] 9.1 Filter-Engine Klasse implementieren
    - `FilterEngine` Klasse erstellen mit `FilterConfig`
    - `apply_filters(industrial_areas, power_lines, water_sources) -> list[dict]` implementieren
    - cKDTree-Index über alle Knoten aller Hochspannungsleitungen erstellen (falls Kriterium B aktiv)
    - `find_nearest_power_line()` mit KDTree-Vorfilterung und exakter Punkt-zu-Segment-Distanz implementieren
    - `find_nearest_water_source()` mit Haversine-Distanz implementieren
    - Nur aktivierte Kriterien anwenden
    - Kein `distance_power_line_km`-Feld wenn Kriterium B deaktiviert
    - Kein `water_source_name`-Feld wenn Kriterium C deaktiviert
    - _Anforderungen: 4.2, 4.3, 4.4, 4.5, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4_

  - [ ]* 9.2 Property-Test: Hochspannungsleitungs-Filter hält Schwellwert ein
    - **Property 6: Hochspannungsleitungs-Filter hält Schwellwert ein**
    - Wenn Kriterium_B aktiviert ist, sollen alle Gebiete in der Ergebnisliste eine minimale Distanz zur nächsten Hochspannungsleitung < konfigurierter Schwellwert haben.
    - **Validiert: Anforderung 4.5**

  - [ ]* 9.3 Property-Test: Wasserquellen-Filter hält Schwellwert ein
    - **Property 7: Wasserquellen-Filter hält Schwellwert ein**
    - Wenn Kriterium_C aktiviert ist, sollen alle Gebiete in der Ergebnisliste eine minimale Distanz zur nächsten Wasserquelle < konfigurierter Schwellwert haben.
    - **Validiert: Anforderung 5.3**

  - [ ]* 9.4 Property-Test: Deaktivierte Kriterien erzeugen keine Felder
    - **Property 8: Deaktivierte Kriterien erzeugen keine Felder**
    - Bei deaktiviertem Kriterium_B: kein distance_power_line_km-Feld. Bei deaktiviertem Kriterium_C: kein water_source_name/distance_water_source_km-Feld.
    - **Validiert: Anforderungen 6.2, 6.3**

  - [ ]* 9.5 Property-Test: Filterung reduziert nur
    - **Property 9: Filterung reduziert nur**
    - Für jede Eingabeliste und Filterkonfiguration soll die Ergebnisliste nie mehr Elemente enthalten als die Eingabeliste.
    - **Validiert: Anforderung 6.4**

  - [ ]* 9.6 Unit-Tests für Filter-Engine
    - Testen mit bekannten Koordinaten und Schwellwerten
    - Testen mit deaktivierten Kriterien
    - Testen mit leeren Eingabelisten
    - _Anforderungen: 4.2, 4.3, 4.4, 4.5, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4_

- [x] 10. Metadaten-Anreicherung implementieren
  - [x] 10.1 MetadataEnricher Klasse implementieren
    - `MetadataEnricher` Klasse erstellen
    - `enrich(filtered_areas, power_lines, water_sources, config) -> list[AreaResult]` implementieren
    - Pflichtfelder setzen: latitude, longitude, area_sqm, industrial_area_name, has_plots_for_sale, plot_sizes_sqm, research_confidence, research_sources
    - Bedingte Felder: distance_power_line_km (wenn Kriterium B aktiv), water_source_name und distance_water_source_km (wenn Kriterium C aktiv)
    - _Anforderungen: 7.1, 7.2, 7.3_

  - [ ]* 10.2 Property-Test: AreaResult enthält alle erforderlichen und bedingten Felder
    - **Property 10: AreaResult enthält alle erforderlichen und bedingten Felder**
    - Jedes AreaResult soll alle Pflichtfelder enthalten. Bei aktivem Kriterium_B: distance_power_line_km. Bei aktivem Kriterium_C: water_source_name und distance_water_source_km.
    - **Validiert: Anforderungen 7.1, 7.2, 7.3**

  - [ ]* 10.3 Unit-Tests für Metadaten-Anreicherung
    - Testen mit verschiedenen Konfigurationskombinationen (B an/aus, C an/aus)
    - Testen der korrekten Zuordnung von Infrastrukturdaten
    - _Anforderungen: 7.1, 7.2, 7.3_

- [x] 11. Checkpoint – Alle Komponenten prüfen
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer konsultieren.

- [x] 12. Pipeline-Integration
  - [x] 12.1 find_areas Hauptfunktion implementieren
    - `find_areas(config_path: str) -> list[AreaResult]` implementieren
    - Pipeline-Schritte in korrekter Reihenfolge: Konfiguration laden → Industriegebiete abfragen → Web-Research → optional Hochspannungsleitungen/Wasserquellen abfragen → filtern → Metadaten anreichern
    - Alle Komponenten zusammenführen
    - _Anforderungen: 9.1, 9.2_

  - [ ]* 12.2 Property-Test: Pipeline-Ausgabe hat gültige Koordinaten
    - **Property 13: Pipeline-Ausgabe hat gültige Koordinaten**
    - Für jedes AreaResult in der Pipeline-Ausgabe: Latitude ∈ [-90, 90] und Longitude ∈ [-180, 180].
    - **Validiert: Anforderung 9.3**

  - [ ]* 12.3 Integrationstests für die Gesamtpipeline
    - End-to-End-Test mit gemockter Overpass API, gemocktem LLM und gemockter Websuch-API
    - Test mit verschiedenen Konfigurationskombinationen (B an/aus, C an/aus)
    - Test mit leeren API-Antworten
    - _Anforderungen: 9.1, 9.2, 9.3_

- [x] 13. Abschluss-Checkpoint
  - Sicherstellen, dass alle Tests bestehen. Bei Fragen den Benutzer konsultieren.

## Hinweise

- Aufgaben mit `*` sind optional und können für ein schnelleres MVP übersprungen werden
- Jede Aufgabe referenziert spezifische Anforderungen für Nachverfolgbarkeit
- Checkpoints stellen inkrementelle Validierung sicher
- Property-Tests validieren universelle Korrektheitseigenschaften aus dem Design-Dokument
- Unit-Tests validieren spezifische Beispiele und Randfälle
- Property-Test-Bibliothek: hypothesis
