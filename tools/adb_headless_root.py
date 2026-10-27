#!/usr/bin/env python3
"""
DFRoot Headless Automated Root Orchestrator via ADB
"""
import os
import sys
import time
import glob
import re
import subprocess
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
APK_DIR = os.path.join(REPO_ROOT, "app", "build", "outputs", "apk", "debug")

APK_PACKAGE = "df.root"
SERVICE_NAME = "df.root.headless.RootService"
FLAG_SUCCESS = "/data/local/tmp/dfroot_success.flag"
FLAG_FAIL = "/data/local/tmp/dfroot_fail.flag"
REMOTE_APK = "/data/local/tmp/ksu.apk"
TIMEOUT_SECS = 60

def run_cmd(cmd, cwd=None):
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True, timeout=120, cwd=cwd)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"

def adb_cmd(serial, cmd):
    s_flag = f"-s {serial} " if serial else ""
    return run_cmd(f"adb {s_flag}{cmd}")

def adb_shell(serial, cmd):
    s_flag = f"-s {serial} " if serial else ""
    return run_cmd(f"adb {s_flag}shell \"{cmd}\"")

# select target device interactively
def select_target_device():
    print("[*] Detecting connected ADB devices...")
    rc, out, _ = run_cmd("adb devices")
    if rc != 0:
        print("[-] ERROR: Failed to run adb devices.")
        sys.exit(1)
    lines = [l for l in out.splitlines()[1:] if l.strip()]
    devices = [l.split()[0] for l in lines if len(l.split()) >= 2 and l.split()[1] == "device"]
    if not devices:
        print("[-] ERROR: No authorized ADB devices found.")
        sys.exit(1)
    if len(devices) == 1:
        return devices[0]
    print(f"\n[?] Found {len(devices)} devices. Select target:")
    dev_infos = []
    for d in devices:
        _, m_out, _ = adb_shell(d, "getprop ro.product.model")
        _, a_out, _ = adb_shell(d, "getprop ro.product.cpu.abi")
        dev_infos.append(f"{d} ({m_out or 'Unknown'}, {a_out or 'Unknown'})")
    idx = 0
    # windows arrow navigation
    if os.name == "nt":
        try:
            import msvcrt
            print("    (Use Up/Down arrows to navigate, Enter to select)\n")
            while True:
                for i, info in enumerate(dev_infos):
                    ptr = ">" if i == idx else " "
                    print(f"  {ptr} [{i+1}] {info}")
                ch = msvcrt.getch()
                if ch == b"\xe0":
                    sub = msvcrt.getch()
                    if sub == b"H": idx = (idx - 1) % len(devices)
                    elif sub == b"P": idx = (idx + 1) % len(devices)
                elif ch == b"\r": break
                elif ch == b"\x03": sys.exit(0)
                # clear lines for redraw
                sys.stdout.write(f"\033[{len(dev_infos)}A")
                sys.stdout.flush()
        except Exception:
            idx = fallback_device_input(dev_infos)
    else:
        idx = fallback_device_input(dev_infos)
    return devices[idx]

def fallback_device_input(dev_infos):
    for i, info in enumerate(dev_infos):
        print(f"  [{i+1}] {info}")
    while True:
        try:
            sel = int(input(f"Enter choice [1-{len(dev_infos)}]: ")) - 1
            if 0 <= sel < len(dev_infos): return sel
        except (ValueError, KeyboardInterrupt): sys.exit(0)

# inspect hardware and kernel
def inspect_device(serial, auto_yes=False):
    _, mfr, _ = adb_shell(serial, "getprop ro.product.manufacturer")
    _, model, _ = adb_shell(serial, "getprop ro.product.model")
    _, andr, _ = adb_shell(serial, "getprop ro.build.version.release")
    _, sdk, _ = adb_shell(serial, "getprop ro.build.version.sdk")
    _, patch, _ = adb_shell(serial, "getprop ro.build.version.security_patch")
    _, abi, _ = adb_shell(serial, "getprop ro.product.cpu.abi")
    _, kver, _ = adb_shell(serial, "uname -r")

    print("\n" + "=" * 65)
    print(" TARGET DEVICE SPECIFICATIONS:")
    print("=" * 65)
    print(f"  Device Serial: {serial}")
    print(f"  Manufacturer:  {mfr or 'Unknown'}")
    print(f"  Model:         {model or 'Unknown'}")
    print(f"  Android OS:    {andr or 'Unknown'} (API {sdk or '?'}, Patch: {patch or 'Unknown'})")
    print(f"  CPU ABI:       {abi or 'Unknown'}")
    print(f"  Linux Kernel:  {kver or 'Unknown'}")
    print("-" * 65)

    # audit compatibility requirements
    compat_abi = (abi == "arm64-v8a")
    major, minor = 0, 0
    m = re.match(r"^(\d+)\.(\d+)", kver or "")
    if m: major, minor = int(m.group(1)), int(m.group(2))
    compat_kernel = (major > 5) or (major == 5 and minor >= 10)
    supported_kmis = [(5, 10), (5, 15), (6, 1), (6, 6), (6, 12), (6, 18)]
    kmi_matched = (major, minor) in supported_kmis

    print(" PRE-FLIGHT COMPATIBILITY AUDIT:")
    if compat_abi: print("  [+] Architecture: arm64-v8a (Supported)")
    else: print(f"  [-] Architecture: {abi} (UNSUPPORTED: DFRoot requires arm64-v8a)")
    if compat_kernel and kmi_matched: print(f"  [+] Kernel:       {major}.{minor} (Supported KMI LKM available)")
    elif compat_kernel: print(f"  [?] Kernel:       {major}.{minor} (Vulnerable base, but LKM KMI may not match)")
    else: print(f"  [-] Kernel:       {major}.{minor} (NOT VULNERABLE: DirtyFrag requires Kernel 5.10+)")
    print("=" * 65)

    if auto_yes:
        print("[*] Auto-confirm flag (-y) provided. Continuing...")
        return

    is_compatible = compat_abi and compat_kernel and kmi_matched
    prompt_msg = "Proceed with exploit on this device? [Y/n]: " if is_compatible else "[!] WARNING: Device appears INCOMPATIBLE. Proceed anyway? [y/N]: "
    try:
        ans = input(prompt_msg).strip().lower()
        if is_compatible and ans in ["n", "no"]: sys.exit(0)
        if not is_compatible and ans not in ["y", "yes"]:
            print("[*] Aborted by user.")
            sys.exit(0)
    except (EOFError, KeyboardInterrupt):
        print("\n[*] Aborted.")
        sys.exit(0)

def check_already_rooted(serial):
    rc, out, _ = adb_shell(serial, "su -c id")
    if rc == 0 and "uid=0" in out:
        print("[+] Device already rooted: " + out)
        return True
    return False

def ensure_apk(apk_arg):
    if apk_arg and os.path.exists(apk_arg):
        return os.path.abspath(apk_arg)
    candidates = glob.glob(os.path.join(APK_DIR, "*.apk"))
    if candidates: return candidates[0]
    print("[*] Building APK with Gradle...")
    cmd = ".\\gradlew.bat :app:assembleDebug" if os.name == "nt" else "./gradlew :app:assembleDebug"
    rc, out, err = run_cmd(cmd, cwd=REPO_ROOT)
    if rc != 0:
        print(f"[-] Gradle build failed:\n{err or out}")
        sys.exit(1)
    candidates = glob.glob(os.path.join(APK_DIR, "*.apk"))
    if not candidates:
        print("[-] Build succeeded but APK file not found.")
        sys.exit(1)
    print(f"[+] Built APK: {candidates[0]}")
    return candidates[0]

def resolve_ksu_apk(ksu_arg):
    if ksu_arg and os.path.exists(ksu_arg): return os.path.abspath(ksu_arg)
    root_candidate = os.path.join(REPO_ROOT, "ksu.apk")
    if os.path.exists(root_candidate): return root_candidate
    return None

def push_ksu_apk(serial, local_path):
    if local_path and os.path.exists(local_path):
        print(f"[*] Pushing {local_path} -> {REMOTE_APK}...")
        rc, _, err = adb_cmd(serial, f"push \"{local_path}\" {REMOTE_APK}")
        if rc == 0:
            adb_shell(serial, f"chmod 666 {REMOTE_APK}")
            print("[+] Pushed ksu.apk successfully.")
        else: print(f"[-] Push failed: {err}")
    else: print("[*] No local ksu.apk. Service will download fallback from GitHub.")

def install_apk(serial, apk_path):
    print(f"[*] Installing {os.path.basename(apk_path)}...")
    rc, _, err = adb_cmd(serial, f"install -r -g \"{apk_path}\"")
    if rc != 0:
        print(f"[-] Install failed: {err}")
        sys.exit(1)
    print("[+] APK installed successfully.")

def cleanup_flags(serial):
    adb_shell(serial, f"rm -f {FLAG_SUCCESS} {FLAG_FAIL} /data/local/tmp/dfroot.log")

# live trace logcat stream
def monitor_with_live_logcat(serial):
    print("\n[*] Starting live exploit logcat stream...")
    adb_cmd(serial, "logcat -c")
    cmd = f"adb -s {serial} logcat -v time -s DFRoot_Headless dfroot"
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, shell=True, bufsize=1)
    start_time = time.time()
    success = False
    failure_reason = None

    try:
        while time.time() - start_time < TIMEOUT_SECS:
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue
            line = line.strip()
            print(f"  | {line}")
            # check success events
            if "ROOT COMPLETED" in line or "Root success" in line:
                success = True
                break
            # check failure events
            if "Root failed" in line or "failed to patch files" in line or "CRITICAL EXCEPTION" in line:
                failure_reason = line
                break
            # check direct su periodic
            rc, out, _ = adb_shell(serial, "su -c id")
            if rc == 0 and "uid=0" in out:
                success = True
                break
    finally:
        try:
            proc.terminate()
            proc.kill()
        except Exception: pass

    if success:
        print("\n[+] SUCCESS: Root trigger reported success!")
        return True
    if failure_reason:
        print(f"\n[-] FAILED: {failure_reason}")
        return False
    print("\n[-] TIMEOUT: No response within timeout limit.")
    return False

def verify(serial, cleanup=True):
    rc, out, _ = adb_shell(serial, "su -c id")
    if rc == 0 and "uid=0" in out:
        print("\n" + "=" * 65)
        print(f"[+++] ROOT VERIFIED SUCCESSFULLY: {out}")
        print("=" * 65 + "\n")
        if cleanup:
            print("[*] Cleaning up DFRoot APK and temporary files...")
            adb_cmd(serial, f"uninstall {APK_PACKAGE}")
            cleanup_flags(serial)
            print("[+] Cleanup complete.")
        return True
    print("[-] Root verification failed: 'su -c id' did not return root.")
    return False

def main():
    parser = argparse.ArgumentParser(description="DFRoot Headless Auto-Root")
    parser.add_argument("-s", "--serial", default=None, help="Specific device serial")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-confirm compatibility warnings")
    parser.add_argument("--apk", default=None, help="Path to DFRoot APK")
    parser.add_argument("--ksu-apk", default="ksu.apk", help="KernelSU-Next APK")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep APK installed")
    args = parser.parse_args()

    serial = args.serial or select_target_device()
    inspect_device(serial, auto_yes=args.yes)
    if check_already_rooted(serial): return
    apk_path = ensure_apk(args.apk)
    ksu_path = resolve_ksu_apk(args.ksu_apk)
    cleanup_flags(serial)
    push_ksu_apk(serial, ksu_path)
    install_apk(serial, apk_path)
    print(f"[*] Triggering {APK_PACKAGE}/{SERVICE_NAME}...")
    adb_shell(serial, f"am start-foreground-service -n {APK_PACKAGE}/{SERVICE_NAME}")
    if monitor_with_live_logcat(serial):
        verify(serial, cleanup=not args.no_cleanup)

if __name__ == "__main__":
    main()
