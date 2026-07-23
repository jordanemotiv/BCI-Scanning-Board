# EMOTIV BCI Assistive Communication System

An interactive, dual-stream Brain-Computer Interface (BCI) communication board designed for nonverbal individuals and individuals with motor impairments. Powered by PyQt6 and the EMOTIV Cortex API, this application converts real-time EEG brain patterns (Mental Commands) and facial EMG expressions into matrix-scanning keyboard selections and text-to-speech outputs.

---

## Repository Scripts

This repository contains three evolutionary versions of the communication board:

| File Script | Description | Status |
| :--- | :--- | :--- |
| `scanningboard.py` | **Original Core Board:** The foundational 2-stage matrix scanner interface without the preflight diagnostic wizard or credential dialogs. | Legacy |
| `scanningboard_setupscreen.py` | **Diagnostics & Visual Update:** Introduces the preflight Contact Quality (CQ) and EEG Quality (EQ) sensor maps with EMOTIV brand styling (`#d9145a` hot-pink). | Intermediate |
| `scanningboard_setupandconfig.py` | **Production Master:** The complete, feature-rich version including in-app API credential setup, caregiver phrase management, live battery/signal diagnostics, TTS synthesis, dynamic sensitivity sliders, and clean exit thread handling. | **Recommended (Latest)** |

---

## Key Features (`scanningboard_setupandconfig.py`)

### Dual-Stream Telemetry Engine
* **Mental Commands (`com`):** Maps `Push` (Select) and `Pull` (Change Speed) intent streams directly to matrix targeting.
* **Facial EMG Expressions (`fac`):** Dual-mapped backup input processing using `Teeth Clench` (Select) and `Brow Furrow / Frown` (Speed Change).
* **Independent Stream Toggles:** Easily enable or disable mental commands or facial expressions independently via bottom checkboxes.

### Real-time Hardware Tuning Bay
* **Thought Sensitivity Slider:** Adjustable trigger activation threshold (0.05 to 0.95, default `0.35`).
* **Facial EMG Sensitivity Slider:** Adjustable trigger activation threshold (0.05 to 0.95, default `0.70`).
* **Cooldown Duration Slider:** Dynamic post-selection pause timer (0.5s to 5.0s, default `2.5s`).

### Caregiver Custom Phrase Manager
* Open the **`📝 Phrases`** dialog on the preflight screen to add, edit, or remove custom words, daily care requests, or family names.
* Automatically saves to `phrases.json` and updates the phrase matrix dynamically.

### ⚙️ In-App API & Profile Configuration
* Open the **`⚙️ API Settings`** modal to input your EMOTIV Developer **Client ID**, **Client Secret**, and trained **Profile Name**.
* Saves credentials to `config.json` and prompts automatically on initial startup if configuration files are missing.

### 🔊 Speech & Editing Controls
* **Offline Text-to-Speech (TTS):** Integrated `pyttsx3` voice engine with an asynchronous worker thread so audio playback never freezes matrix scanning.
* **Single-Character Backspace:** Edit messages tile-by-tile via the `⌫ BACKSPACE` button without clearing the entire sentence.
* **Scanner Pause/Resume:** Freeze matrix cycling at any time using the `⏸️ PAUSE` button or the `P` key on your keyboard.

### Live Device & Cooldown Diagnostics
* **Battery & Signal Status:** Live real-time telemetry displaying headset battery percentage (`🔋`) and signal quality strength (`📶`).
* **Telemetry Cooldown Banner:** Prominent live visual countdown (`⏳ BCI PAUSE — RESUMING IN 2.1s`) rendered directly in the top state tracker during selection locks.

---

## 🛠️ Installation & Prerequisites

### 1. Hardware & Software Requirements
* An **EMOTIV Insight** or **EPOC/EPOC+** headset.
* **EMOTIV Launcher** installed and running in the background (enables the local Cortex WebSocket service at `wss://localhost:6868`).
* Python installed on your system.

### 2. Install Required Python Libraries

Run the following command in your terminal:

```bash
pip install PyQt6 pyttsx3
