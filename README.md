# Supercell (.sc) / Adobe Flash XFL Recursive Asset Renderer

Ein leistungsstarkes Python-CLI-Tool zum rekursiven Parsen und Rendern von Supercell (`.sc`) / Adobe Flash XFL-Projekten. Das Skript rekonstruiert aus den XML-Hierarchien und einzelnen PNG-Texturen die originalen Grafiken sowie Animationen als statische PNGs, transparente animated GIFs, hochauflösende APNGs sowie interaktive **HTML5 Canvas JS Real-Time Player**.

---

## 🌟 Features

- **Reine In-Memory Archiv-Verarbeitung**: Liest `.fla`- und `.zip`-Dateien zu 100% direkt aus dem Arbeitsspeicher (RAM) – ohne Entpacken auf die Festplatte!
- **Flexible Eingabeformate (`-i`)**: Akzeptiert `.fla`-Dateien, `.zip`-Archive oder bereits entpackte Ordner.
- **Rekursiver XML-Tree-Parser**: Liest verschachtelte Symbole (`exports` $\rightarrow$ `movieclips` $\rightarrow$ `shapes` $\rightarrow$ `resources`).
- **Mathematisch exakte Matrizen-Transformation**: Verarbeitet 2D-Affine-Transformationsmatrizen (Skalierung, Rotation, Translation, Scherung).
- **Farb- & Alpha-Korrektur**: Unterstützt Flash-Farbtransformationen (`alphaMultiplier`, Multiplikatoren, Offsets).
- **HTML5 Canvas JS Web-Export (`--export-js`)**: Generiert einen eigenständigen JavaScript Canvas-Player + Animationsdaten (`animations_data.js`). Rendert 60 FPS Animationen direkt auf der GPU des Browsers – sowohl lokal als auch auf jedem Webserver!
- **Korrigierter Transparenz-GIF-Export**: Verhindert schwarze Ränder und Artefakte durch optimierte Palettenquantisierung (`transparency=255`).
- **32-Bit APNG Support**: Erstellt animierte PNGs in echter 32-Bit TrueColor Alpha-Qualität.
- **Saubere Ordnerstruktur**: Trennt statische Bilder, GIFs, APNGs, Web-Player und Frame-Sequenzen in eigene Unterordner.
- **Interaktives Web-Dashboard (`index.html`)**: Generiert automatisch eine moderne dunkle Vorschau-Galerie im Browser.

---

## 🛠️ Einrichten der Python-Umgebung (Virtual Environment)

Um Fehlerquellen mit System-Bibliotheken oder veralteten Paketen auszuschließen, wird eine virtuelle Python-Umgebung (venv) empfohlen:

### 1. Virtuelle Umgebung (venv) erstellen

Öffne ein Terminal im Projektordner und führe aus:

```bash
python -m venv venv
```

### 2. Virtuelle Umgebung aktivieren

- **Windows (PowerShell)**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
  *(Falls ein Skriptausführungs-Fehler auftritt, einmalig `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` ausführen).*

- **Windows (CMD / Eingabeaufforderung)**:
  ```cmd
  venv\Scripts\activate.bat
  ```

- **Linux / macOS**:
  ```bash
  source venv/bin/activate
  ```

### 3. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

---

## 🚀 Nutzung & CLI-Parameter

```bash
python xfl_renderer.py -i .\ressources\"InputFilename" -o .\ressources\"OutputFolder" [OPTIONEN]
```

### Parameterübersicht

| Parameter | Kurzform | Standard | Beschreibung |
| :--- | :--- | :--- | :--- |
| `--input` | `-i` | *(erforderlich)* | Pfad zur `.fla`-Datei, `.zip`-Datei oder entpacktem Ordner |
| `--output` | `-o` | *(erforderlich)* | Zielordner für die gerenderten Dateien |
| `--export-js` | | `False` | **Generiert den HTML5 Canvas JS Player & `animations_data.js`** (für Webapps) |
| `--limit` | `-n` | `None` (alle) | **Anzahl zu rendernder Assets beschränken** (ideal für schnelle Testläufe!) |
| `--export-frames` | | `False` | **Aktiviert den Export einzelner PNG-Frames** in eigenen Unterordnern |
| `--fps` | | `30` | Framerate für animierte GIFs und APNGs |
| `--scale` | | `1.0` | Skalierungsfaktor für die Ausgabegröße (z.B. `0.5` oder `2.0`) |
| `--format` | | `png gif apng` | Gewünschte Exportformate (`png`, `gif`, `apng`, `frames`) |

---

## 💡 Beispiele

### 1. Schnelltest: Nur die ersten 3 Assets aus einer `.fla` / `.zip` Datei rendern
```bash
python xfl_renderer.py -i .\ressources\"InputFilename.fla" -o .\ressources\"OutputFolder" -n 3
```

### 2. Vollständiger Web-Export für Webapps (HTML5 Canvas Player + GIFs + PNGs)
```bash
python xfl_renderer.py -i .\ressources\"InputFilename.zip" -o .\ressources\"OutputFolder" --export-js
```

### 3. Vollständiger Render mit PNG-Frame-Sequenzen & 2x Skalierung
```bash
python xfl_renderer.py -i .\ressources\"InputFilename" -o .\ressources\"OutputFolder" --scale 2.0 --export-frames
```

---

## 📁 Ausgabestruktur

```
OutputFolder/
├── 📁 static/                # Statische PNG-Grafiken & Animation-Vorschaubilder
├── 📁 animations_gif/        # Transparent animierte GIFs
├── 📁 animations_apng/       # Animierte PNGs in TrueColor Alpha-Qualität
├── 📁 web_js_player/         # (Via --export-js) HTML5 Canvas JS Player & Animationsdaten
│   ├── 📄 player.html        # Standalone HTML5 Canvas Player (60 FPS)
│   ├── 📄 animations_data.js # Animationsdaten (Matrizen & Frames, lokal & webkompatibel)
│   └── 📁 textures/          # Einzelne Textur-PNGs
├── 📁 frame_sequences/       # (Via --export-frames) PNG-Einzelframes pro Animation
└── 📄 index.html             # Interaktives Web-Dashboard zur Vorschau aller Assets
```
