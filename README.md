<p align="center">
  <img src=".github/icon.png" width="96" />
</p>

# DFRoot Headless [Automated ADB Root Edition]

DFRoot Headless is an automated, headless fork of [DFRoot](https://github.com/diabl0w/DFRoot) leveraging the DirtyFrag vulnerability (**CVE-2026-43284**).

This fork completely eliminates the need for any on-device GUI interaction or installed SU Manager app (such as KernelSU / KernelSU-Next APK). It operates as a silent **Headless Foreground Service** orchestrated entirely from your PC via ADB, granting instantaneous `su` root access to ADB shell (`UID 2000`).

---

## Key Fork Features

- **Headless Worker Architecture:** All Activities, Settings screens, and launchers have been stripped. DFRoot runs as an exported Android Foreground Service (`df.root.headless.RootService`).
- **No Manager App Required:** You do not need to install KernelSU or KernelSU-Next APK on your device. The service dynamically extracts `libksud.so` from a local APK or downloads the official release directly from GitHub in memory.
- **Immediate Shell Root (`--allow-shell`):** Patches the userspace bootstrap to launch `ksud late-load` with `--allow-shell`, allowing `adb shell` to execute `su` without requiring a GUI grant dialog.
- **Kernel Vermagic & Safety Audit:** Features an embedded ELF64 `.modinfo` parser in `bootstrap.c` that validates kernel module vermagic against `uname -r` prior to execution, preventing kernel panic/bootloops.
- **Interactive 1-Click PC Tool (`tools/adb_headless_root.py`):**
  - **Auto-Build:** Detects missing APK and automatically compiles it using local Gradle wrapper.
  - **Interactive Device Selector:** Multi-device selection with arrow keys (`Up` / `Down` / `Enter`).
  - **Pre-flight Audit:** Inspects Manufacturer, Model, Android Version, CPU ABI, and Linux Kernel compatibility.
  - **Live Logcat Streaming:** Real-time log trace with instant error diagnostics (no hanging/timeouts).
  - **Automated Verification & Cleanup:** Verifies `su -c id` and cleans up temporary files on the device.

---

## Supported Environments

- **Target Architecture:** `arm64-v8a` only (AArch64).
- **Target Android Versions:** Android 12 through Android 17 (API 31 - 36).
- **Vulnerable Linux Kernels:** 5.10, 5.15, 6.1, 6.6, 6.12, 6.18.

---

## Quick Start (1-Click Root via PC)

### 1. Requirements on PC
- Python 3.8+
- Android SDK Platform-Tools (`adb` added to PATH)
- Connected Android device with **USB Debugging** enabled

### 2. Run the Automated Orchestrator

Open terminal in the project directory and run:

```bash
# Windows
python .\tools\adb_headless_root.py

# Linux / macOS
python3 tools/adb_headless_root.py
```

The script will:
1. Detect connected devices (presents an interactive menu if multiple devices are attached).
2. Audit device specs (Manufacturer, Kernel, Android OS, ABI).
3. Auto-compile `DFRoot_4.8-headless.apk` if not already built.
4. Push and install the headless package.
5. Trigger `RootService` via ADB and stream the exploit execution logcat in real-time.
6. Verify root privileges (`su -c id`) and clean up the temporary APK.

---

## Advanced CLI Options

```text
usage: adb_headless_root.py [-h] [-s SERIAL] [-y] [--apk APK] [--ksu-apk KSU_APK] [--no-cleanup]

options:
  -h, --help           Show this help message and exit
  -s, --serial SERIAL  Target specific device serial
  -y, --yes            Auto-confirm compatibility warnings (non-interactive mode)
  --apk APK            Path to custom DFRoot APK (built automatically if omitted)
  --ksu-apk KSU_APK    Path to local KernelSU-Next APK (auto-downloaded from GitHub if omitted)
  --no-cleanup         Keep DFRoot APK installed on device after success
```

---

## Manual Execution via ADB Shell

If you prefer executing steps manually:

```bash
# 1. Build the APK (if not already compiled)
./gradlew :app:assembleDebug

# 2. Push KernelSU-Next APK (optional, service can download automatically)
adb push ksu.apk /data/local/tmp/ksu.apk
adb shell chmod 666 /data/local/tmp/ksu.apk

# 3. Install DFRoot Headless APK
adb install -r -g app/build/outputs/apk/debug/DFRoot_4.8-headless.apk

# 4. Trigger Headless RootService
adb shell am start-foreground-service -n df.root/df.root.headless.RootService

# 5. Monitor real-time logs
adb logcat -s DFRoot_Headless dfroot

# 6. Verify root
adb shell su -c id
```

---

## Building from Source

To compile the headless APK manually on your workstation:

```bash
# Windows
.\gradlew.bat :app:assembleDebug

# Linux / macOS
./gradlew :app:assembleDebug
```

Built APK will be located at:
`app/build/outputs/apk/debug/DFRoot_4.8-headless.apk`

---

## Credits & Upstream

- **Original DFRoot Project:** [diabl0w/DFRoot](https://github.com/diabl0w/DFRoot)
- **KernelSU-Next:** [KernelSU-Next/KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next)
- **DirtyFrag Vulnerability (CVE-2026-43284) PoC:** [lsposed/lspromise](https://github.com/lsposed/lspromise) & [V4bel/dirtyfrag](https://github.com/V4bel/dirtyfrag)
- **SELinux Permissive kernel modules:** [polygraphene/DFReroot](https://github.com/polygraphene/DFReroot)
