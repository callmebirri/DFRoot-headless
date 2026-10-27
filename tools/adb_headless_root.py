#!/usr/bin/env python3
"""
DFRoot Headless Automated Root Orchestrator via ADB
"""
import os
import sys
import time
import glob
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
TIMEOUT_SECS = 120

def run_cmd(cmd, cwd=None):
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True, timeout=120, cwd=cwd)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"

def adb_shell(cmd):
    return run_cmd(f"adb shell \"{cmd}\"")

def check_device():
    print("[*] Checking connected ADB devices...")
    rc, out, _ = run_cmd("adb devices")
    lines = [l for l in out.splitlines()[1:] if l.strip() and "device" in l]
    if not lines:
        print("[-] ERROR: No ADB device connected.")
        sys.exit(1)
    print(f"[+] Device connected: {lines[0].split()[0]}")

def check_already_rooted():
    rc, out, _ = adb_shell("su -c id")
    if rc == 0 and "uid=0" in out:
        print("[+] Device already rooted: " + out)
        return True
    return False

def ensure_apk(apk_arg):
    if apk_arg and os.path.exists(apk_arg):
        return os.path.abspath(apk_arg)
    candidates = glob.glob(os.path.join(APK_DIR, "*.apk"))
    if candidates:
        return candidates[0]
    print("[*] APK not found. Automatically building with Gradle...")
    gradle_cmd = ".\\gradlew.bat :app:assembleDebug" if os.name == "nt" else "./gradlew :app:assembleDebug"
    rc, out, err = run_cmd(gradle_cmd, cwd=REPO_ROOT)
    if rc != 0:
        print(f"[-] Gradle build failed:\n{err or out}")
        sys.exit(1)
    candidates = glob.glob(os.path.join(APK_DIR, "*.apk"))
    if not candidates:
        print("[-] Build succeeded but APK file not found.")
        sys.exit(1)
    print(f"[+] Successfully built: {candidates[0]}")
    return candidates[0]

def resolve_ksu_apk(ksu_arg):
    if ksu_arg and os.path.exists(ksu_arg):
        return os.path.abspath(ksu_arg)
    root_candidate = os.path.join(REPO_ROOT, "ksu.apk")
    if os.path.exists(root_candidate):
        return root_candidate
    return None

def push_ksu_apk(local_path):
    if local_path and os.path.exists(local_path):
        print(f"[*] Pushing {local_path} -> {REMOTE_APK}...")
        rc, _, err = run_cmd(f"adb push \"{local_path}\" {REMOTE_APK}")
        if rc == 0:
            adb_shell(f"chmod 666 {REMOTE_APK}")
            print("[+] KSU APK pushed successfully.")
        else:
            print(f"[-] Push failed: {err}")
    else:
        print("[*] No local APK provided. Service will download fallback from GitHub.")

def install_apk(apk_path):
    print(f"[*] Installing {apk_path}...")
    rc, _, err = run_cmd(f"adb install -r -g \"{apk_path}\"")
    if rc != 0:
        print(f"[-] Install failed: {err}")
        sys.exit(1)
    print("[+] APK installed successfully.")

def cleanup_flags():
    adb_shell(f"rm -f {FLAG_SUCCESS} {FLAG_FAIL} /data/local/tmp/dfroot.log")

def trigger_service():
    print(f"[*] Starting {APK_PACKAGE}/{SERVICE_NAME}...")
    rc, out, err = adb_shell(f"am start-foreground-service -n {APK_PACKAGE}/{SERVICE_NAME}")
    if rc != 0:
        rc, out, err = adb_shell(f"am startservice -n {APK_PACKAGE}/{SERVICE_NAME}")
    print(f"[+] Service trigger response: {out or err}")

def monitor_progress():
    print("[*] Waiting for exploit completion...")
    start = time.time()
    while time.time() - start < TIMEOUT_SECS:
        _, out, _ = adb_shell(f"test -f {FLAG_SUCCESS} && echo OK")
        if "OK" in out:
            print("\n[+] Success flag detected!")
            return True
        _, out_f, _ = adb_shell(f"test -f {FLAG_FAIL} && echo FAIL")
        if "FAIL" in out_f:
            print("\n[-] Exploit failed. Checking logs:")
            _, log_data, _ = adb_shell("cat /data/local/tmp/dfroot.log")
            print(log_data)
            return False
        rc_su, out_su, _ = adb_shell("su -c id")
        if rc_su == 0 and "uid=0" in out_su:
            print(f"\n[+] Root verified via su: {out_su}")
            return True
        print(".", end="", flush=True)
        time.sleep(3)
    print("\n[-] Timed out waiting for root.")
    return False

def verify(cleanup=True):
    rc, out, _ = adb_shell("su -c id")
    if rc == 0 and "uid=0" in out:
        print(f"\n=======================================================")
        print(f"[+] ROOT SUCCESSFUL: {out}")
        print(f"=======================================================\n")
        if cleanup:
            print("[*] Cleaning up DFRoot APK and flags...")
            run_cmd(f"adb uninstall {APK_PACKAGE}")
            cleanup_flags()
            print("[+] Cleanup complete.")
        return True
    return False

def main():
    parser = argparse.ArgumentParser(description="DFRoot Headless Auto-Root")
    parser.add_argument("--apk", default=None, help="Path to DFRoot APK (auto-detected or built if omitted)")
    parser.add_argument("--ksu-apk", default="ksu.apk", help="KernelSU-Next APK")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep APK installed")
    args = parser.parse_args()

    check_device()
    if check_already_rooted():
        return
    apk_path = ensure_apk(args.apk)
    ksu_path = resolve_ksu_apk(args.ksu_apk)
    cleanup_flags()
    push_ksu_apk(ksu_path)
    install_apk(apk_path)
    trigger_service()
    if monitor_progress():
        verify(cleanup=not args.no_cleanup)

if __name__ == "__main__":
    main()
