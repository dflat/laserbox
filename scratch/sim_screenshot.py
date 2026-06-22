"""Boot the real simulator, screenshot the GameSelect menu, inject a keypress
to arm button 0, screenshot again, then shut the simulator down."""
import subprocess, time, os, sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
proc = subprocess.Popen([sys.executable, "-m", "src", "-s"], cwd=root,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(2.5)  # let the window open and boot into GameSelect
    subprocess.run(["grim", "/tmp/laserbox_menu_boot.png"])
    print("boot screenshot -> /tmp/laserbox_menu_boot.png")
    subprocess.run(["wtype", "0"])  # press key '0' => button 0 (arm Golf)
    time.sleep(0.6)
    subprocess.run(["grim", "/tmp/laserbox_menu_armed.png"])
    print("armed screenshot -> /tmp/laserbox_menu_armed.png")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()
print("done")
