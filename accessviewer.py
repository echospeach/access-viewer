"""
AccessViewer - view and control customers' Android phones with broken screens.

Built on scrcpy (https://github.com/Genymobile/scrcpy), free and open source.
Put the scrcpy folder (from the official GitHub release) next to this file.
"""

import csv
import datetime
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

APP_NAME = "AccessViewer"
VERSION = "1.0"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
LOG_FILE = os.path.join(APP_DIR, "customer_log.csv")
SESSION_FILE = os.path.join(APP_DIR, "last_session_output.txt")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WIN else 0
MOD_KEY = "Cmd" if IS_MAC else "Alt"

LOG_COLUMNS = ["date_time", "customer_name", "contact_number", "phone_model",
               "problem", "action", "device_serial"]

STATE_TEXT = {
    "device": ("Ready - USB debugging is ON. Click 'Mirror & Control'.", "#1a7f37"),
    "unauthorized": ("Phone is asking 'Allow USB debugging?'. Accept it on the "
                     "phone (use OTG Control if touch is broken), then Refresh.", "#b35900"),
    "offline": ("Phone is offline. Unplug it, plug it back in, then Refresh.", "#b35900"),
    "recovery": ("Phone is in recovery mode. Restart it normally.", "#b35900"),
    "sideload": ("Phone is in sideload mode. Restart it normally.", "#b35900"),
}

GUIDE_TEXT = f"""HOW TO TURN ON USB DEBUGGING WHEN THE TOUCHSCREEN IS BROKEN

You need to SEE the phone's screen for this. If the screen is completely
black, connect the phone to a monitor with a USB-C to HDMI adapter first
(only some phones support this, e.g. many Samsung flagships).

1. Plug the phone into this computer with a DATA USB cable.
2. Click "OTG Control". A small window opens. Click inside it:
   your mouse and keyboard now control the phone.
   Press {MOD_KEY} to free your mouse again.
3. Let the customer unlock the phone (PIN / pattern / password).
4. Open Settings > About phone.
   - Samsung: Settings > About phone > Software information
   - Xiaomi: Settings > About phone
5. Tap "Build number" 7 times (Xiaomi: tap "MIUI version" or "OS version").
   Enter the PIN if asked. You will see "You are now a developer".
6. Go to Developer options:
   - Most phones: Settings > System > Developer options
   - Samsung: Settings > Developer options (at the bottom)
   - Xiaomi: Settings > Additional settings > Developer options
7. Turn ON "USB debugging".
   Xiaomi: also turn on "USB debugging (Security settings)" or mouse and
   keyboard control will not work.
8. Close the OTG window. Unplug the phone and plug it back in.
9. The phone shows "Allow USB debugging?". Press Allow
   (open OTG Control again if you need the mouse to press it).
   Do NOT tick "Always allow" - this is the customer's phone.
10. Click Refresh in AccessViewer. When it says Ready,
    click "Mirror & Control".

WHEN YOU ARE DONE
Click "Turn off USB debugging" so the customer's phone is left as it was,
then "Finish & save to log".

TROUBLESHOOTING
- Nothing detected: try another cable (many are charge-only) or USB port.
- OTG fails on Windows: close other phone software, unplug/replug, try again.
- Mirror is slow or fails on an old phone: tick "Lower quality" and retry.
"""


def find_tool(name):
    """Find adb / scrcpy next to this app, in a scrcpy* subfolder, or on PATH."""
    exe = name + (".exe" if IS_WIN else "")
    candidates = [os.path.join(APP_DIR, exe)]
    try:
        for entry in sorted(os.listdir(APP_DIR), reverse=True):
            folder = os.path.join(APP_DIR, entry)
            if entry.lower().startswith("scrcpy") and os.path.isdir(folder):
                candidates.append(os.path.join(folder, exe))
    except OSError:
        pass
    for path in candidates:
        if os.path.isfile(path):
            return path
    return shutil.which(name)


def parse_adb_devices(text):
    """Parse the output of 'adb devices -l' into a list of dicts."""
    devices = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("*") or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        info = {}
        for part in parts[2:]:
            if ":" in part:
                key, value = part.split(":", 1)
                info[key] = value
        devices.append({
            "serial": parts[0],
            "state": parts[1],
            "model": info.get("model", "").replace("_", " "),
        })
    return devices


def append_log(row):
    new_file = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


class AccessViewer:
    def __init__(self, root):
        self.root = root
        self.adb = find_tool("adb")
        self.scrcpy = find_tool("scrcpy")
        self.devices = []
        self.refreshing = False
        self.ui_queue = queue.Queue()  # worker threads -> UI thread

        root.title(f"{APP_NAME} {VERSION}")
        root.minsize(560, 640)
        self._build_ui()
        self._update_tool_status()
        self.refresh_devices()
        self._auto_refresh()
        self._process_queue()

    def _process_queue(self):
        """Run UI updates queued by background threads (Tk is not thread-safe)."""
        try:
            while True:
                func, args = self.ui_queue.get_nowait()
                func(*args)
        except queue.Empty:
            pass
        self.root.after(100, self._process_queue)

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 4}
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text=APP_NAME, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(main, text="View and control phones with broken screens").pack(anchor="w")

        # Customer
        cust = ttk.LabelFrame(main, text="1. Customer", padding=8)
        cust.pack(fill="x", pady=(10, 4))
        self.fields = {}
        for row, (key, label) in enumerate([
            ("customer_name", "Customer name"),
            ("contact_number", "Contact number"),
            ("phone_model", "Phone model"),
            ("problem", "Problem"),
        ]):
            ttk.Label(cust, text=label).grid(row=row, column=0, sticky="w", **pad)
            entry = ttk.Entry(cust, width=40)
            entry.grid(row=row, column=1, sticky="ew", **pad)
            self.fields[key] = entry
        cust.columnconfigure(1, weight=1)
        self.consent = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            cust, variable=self.consent,
            text="Customer is present, owns this phone and agrees to me accessing it",
        ).grid(row=4, column=0, columnspan=2, sticky="w", **pad)

        # Phone
        phone = ttk.LabelFrame(main, text="2. Phone", padding=8)
        phone.pack(fill="x", pady=4)
        top = ttk.Frame(phone)
        top.pack(fill="x")
        self.device_var = tk.StringVar()
        self.device_box = ttk.Combobox(top, textvariable=self.device_var,
                                       state="readonly", width=45)
        self.device_box.pack(side="left", fill="x", expand=True)
        self.device_box.bind("<<ComboboxSelected>>", lambda e: self._show_state())
        ttk.Button(top, text="Refresh", command=self.refresh_devices).pack(side="left", padx=6)
        self.state_label = tk.Label(phone, text="Checking...", wraplength=500,
                                    justify="left", font=("Segoe UI", 10, "bold"))
        self.state_label.pack(anchor="w", pady=(8, 2))
        self.tool_label = ttk.Label(phone, text="", foreground="#555")
        self.tool_label.pack(anchor="w")

        # Options
        opts = ttk.LabelFrame(main, text="Options", padding=8)
        opts.pack(fill="x", pady=4)
        self.opt_awake = tk.BooleanVar(value=True)
        self.opt_screen_off = tk.BooleanVar(value=False)
        self.opt_low = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Keep phone awake while connected",
                        variable=self.opt_awake).pack(anchor="w")
        ttk.Checkbutton(opts, text="Turn the phone's own screen off while mirroring",
                        variable=self.opt_screen_off).pack(anchor="w")
        ttk.Checkbutton(opts, text="Lower quality (for old or slow phones)",
                        variable=self.opt_low).pack(anchor="w")

        # Actions
        act = ttk.LabelFrame(main, text="3. Actions", padding=8)
        act.pack(fill="x", pady=4)
        buttons = [
            ("Mirror & Control", self.mirror),
            ("OTG Control (USB debugging off)", self.otg),
            ("Guide: turn on USB debugging", self.show_guide),
            ("Turn off USB debugging", self.disable_debugging),
            ("Finish & save to log", self.finish),
            ("Open customer log", self.open_log),
        ]
        for i, (text, cmd) in enumerate(buttons):
            ttk.Button(act, text=text, command=cmd).grid(
                row=i // 2, column=i % 2, sticky="ew", padx=4, pady=4)
        act.columnconfigure(0, weight=1)
        act.columnconfigure(1, weight=1)

    def _update_tool_status(self):
        missing = [n for n, p in (("scrcpy", self.scrcpy), ("adb", self.adb)) if not p]
        if missing:
            self.tool_label.config(
                text=f"Missing: {', '.join(missing)}. Put the scrcpy folder next to "
                     f"accessviewer.py (see README).", foreground="#c0392b")
        else:
            self.tool_label.config(text="scrcpy and adb found.", foreground="#555")

    # ---------- device detection ----------
    def _auto_refresh(self):
        self.refresh_devices()
        self.root.after(3000, self._auto_refresh)

    def refresh_devices(self):
        if self.refreshing or not self.adb:
            if not self.adb:
                self._set_state("adb not found - see README.", "#c0392b")
            return
        self.refreshing = True
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        try:
            out = subprocess.run([self.adb, "devices", "-l"], capture_output=True,
                                 text=True, timeout=15, creationflags=NO_WINDOW).stdout
            devices = parse_adb_devices(out)
        except (OSError, subprocess.SubprocessError):
            devices = []
        self.ui_queue.put((self._apply_devices, (devices,)))

    def _apply_devices(self, devices):
        self.refreshing = False
        old = self.device_var.get()
        self.devices = devices
        labels = [self._device_label(d) for d in devices]
        self.device_box["values"] = labels
        if old in labels:
            self.device_var.set(old)
        elif labels:
            self.device_var.set(labels[0])
        else:
            self.device_var.set("")
        self._show_state()

    @staticmethod
    def _device_label(d):
        return f"{d['model'] or 'Unknown phone'}  ({d['serial']})  [{d['state']}]"

    def _selected(self):
        label = self.device_var.get()
        for d in self.devices:
            if self._device_label(d) == label:
                return d
        return None

    def _show_state(self):
        d = self._selected()
        if not d:
            self._set_state(
                "No phone with USB debugging detected. If a phone is plugged in, "
                "debugging is probably off: use 'OTG Control' and the Guide.", "#555")
            return
        text, color = STATE_TEXT.get(d["state"], (f"Phone state: {d['state']}", "#555"))
        self._set_state(text, color)
        if d["model"] and not self.fields["phone_model"].get():
            self.fields["phone_model"].insert(0, d["model"])

    def _set_state(self, text, color):
        self.state_label.config(text=text, fg=color)

    # ---------- helpers ----------
    def _check_consent(self):
        if not self.fields["customer_name"].get().strip():
            messagebox.showwarning(APP_NAME, "Enter the customer's name first.")
            return False
        if not self.consent.get():
            messagebox.showwarning(APP_NAME, "Tick the consent box first.")
            return False
        return True

    def _log(self, action, serial=""):
        row = {k: self.fields[k].get().strip() for k in self.fields}
        row.update(date_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   action=action, device_serial=serial)
        try:
            append_log(row)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Could not write the log:\n{e}")

    def _launch_scrcpy(self, args, action, serial=""):
        if not self.scrcpy:
            messagebox.showerror(APP_NAME, "scrcpy not found. See README for setup.")
            return
        env = os.environ.copy()
        if self.adb:
            env["ADB"] = self.adb  # scrcpy uses this adb
        title = f"{APP_NAME} - {self.fields['customer_name'].get().strip()}"
        cmd = [self.scrcpy, "--window-title", title] + args
        try:
            out = open(SESSION_FILE, "w", encoding="utf-8")
            proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT,
                                    cwd=os.path.dirname(self.scrcpy), env=env,
                                    creationflags=NO_WINDOW)
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Could not start scrcpy:\n{e}")
            return
        self._log(action, serial)
        threading.Thread(target=self._watch, args=(proc, out), daemon=True).start()

    def _watch(self, proc, out):
        code = proc.wait()
        out.close()
        if code != 0:
            try:
                with open(SESSION_FILE, encoding="utf-8", errors="replace") as f:
                    tail = "".join(f.readlines()[-12:])
            except OSError:
                tail = ""
            self.ui_queue.put((messagebox.showerror, (
                APP_NAME, f"scrcpy stopped with an error (code {code}).\n\n{tail}")))

    # ---------- actions ----------
    def mirror(self):
        if not self._check_consent():
            return
        d = self._selected()
        if not d or d["state"] != "device":
            messagebox.showinfo(APP_NAME, "No ready phone. USB debugging must be on "
                                "and allowed. Use OTG Control and the Guide first.")
            return
        args = ["-s", d["serial"]]
        if self.opt_awake.get():
            args.append("--stay-awake")
        if self.opt_screen_off.get():
            args.append("--turn-screen-off")
        if self.opt_low.get():
            args += ["--max-size=1024", "--max-fps=30"]
        self._launch_scrcpy(args, "mirror_and_control", d["serial"])

    def otg(self):
        if not self._check_consent():
            return
        messagebox.showinfo(
            APP_NAME,
            "OTG Control: a small window will open. Click inside it - your mouse "
            f"and keyboard then control the phone. Press {MOD_KEY} to free your mouse.\n\n"
            "There is no picture of the phone in this mode: look at the phone itself "
            "(or a monitor via a USB-C to HDMI adapter).")
        self._launch_scrcpy(["--otg"], "otg_control")

    def show_guide(self):
        win = tk.Toplevel(self.root)
        win.title(f"{APP_NAME} - Guide")
        win.geometry("640x620")
        text = tk.Text(win, wrap="word", font=("Consolas", 10), padx=10, pady=10)
        text.insert("1.0", GUIDE_TEXT)
        text.config(state="disabled")
        text.pack(fill="both", expand=True)

    def disable_debugging(self):
        d = self._selected()
        if not d or d["state"] != "device":
            messagebox.showinfo(APP_NAME, "No ready phone connected.")
            return
        if not messagebox.askyesno(APP_NAME, "Turn off USB debugging on this phone? "
                                   "The mirror will disconnect."):
            return
        try:
            subprocess.run([self.adb, "-s", d["serial"], "shell", "settings", "put",
                            "global", "adb_enabled", "0"], capture_output=True,
                           timeout=15, creationflags=NO_WINDOW)
        except (OSError, subprocess.SubprocessError) as e:
            messagebox.showerror(APP_NAME, f"Failed:\n{e}")
            return
        self._log("usb_debugging_turned_off", d["serial"])
        self.root.after(1500, self.refresh_devices)
        messagebox.showinfo(APP_NAME, "Done. If the phone still shows as Ready after "
                            "Refresh, turn it off manually in Developer options.")

    def finish(self):
        if not self.fields["customer_name"].get().strip():
            messagebox.showwarning(APP_NAME, "No customer to finish.")
            return
        d = self._selected()
        if d and d["state"] == "device" and not messagebox.askyesno(
                APP_NAME, "USB debugging is still ON for this phone. Finish anyway?"):
            return
        self._log("session_finished", d["serial"] if d else "")
        for entry in self.fields.values():
            entry.delete(0, "end")
        self.consent.set(False)
        messagebox.showinfo(APP_NAME, "Saved to the customer log. Ready for the next customer.")

    def open_log(self):
        if not os.path.exists(LOG_FILE):
            messagebox.showinfo(APP_NAME, "No log yet.")
            return
        try:
            if IS_WIN:
                os.startfile(LOG_FILE)
            elif IS_MAC:
                subprocess.Popen(["open", LOG_FILE])
            else:
                subprocess.Popen(["xdg-open", LOG_FILE])
        except OSError as e:
            messagebox.showerror(APP_NAME, f"Could not open the log:\n{e}")


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if IS_WIN else "clam")
    except tk.TclError:
        pass
    AccessViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
