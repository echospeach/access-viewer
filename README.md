# AccessViewer

View and control customers' Android phones with broken screens, from your computer.
Built on scrcpy (free, open source).

## Setup (Windows, one time)

1. Install Python from https://www.python.org/downloads/ — tick **"Add python.exe to PATH"** during install.
2. Download scrcpy **only** from the official page: https://github.com/Genymobile/scrcpy/releases
   Get the file named `scrcpy-win64-vX.X.zip`.
3. Extract it **into this AccessViewer folder**. You should end up with:
   ```
   AccessViewer/
     accessviewer.py
     Start AccessViewer.bat
     scrcpy-win64-vX.X/   <- contains scrcpy.exe and adb.exe
   ```
4. Double-click **Start AccessViewer.bat**.

Mac: `brew install scrcpy` then `python3 accessviewer.py`.
Linux: install scrcpy (snap gives the newest) and `python3-tk`, then `python3 accessviewer.py`.

## How to use with a customer

1. Fill in the customer's details and tick the consent box.
2. Plug the phone in with a **data** USB cable.
3. If AccessViewer says **Ready** → click **Mirror & Control**. The phone appears on your screen; use your mouse and keyboard.
4. If no phone is detected → USB debugging is off. Click **Guide** and use **OTG Control** to turn it on.
5. When finished → **Turn off USB debugging**, then **Finish & save to log**.

## What it can and cannot do

| Phone situation | Works? |
|---|---|
| Android, screen shows a picture, touch broken | Yes — OTG Control to enable debugging, then full mirror |
| Android, screen black, phone supports USB-C video out | Yes — use a USB-C to HDMI adapter + OTG Control |
| Android, screen black, no video out, debugging off | No — needs a screen replacement |
| Android with USB debugging already on | Yes — Mirror & Control straight away |
| iPhone | No — iPhones can't be controlled this way |
| Locked phone, customer doesn't know the PIN | No — and it must never try to bypass it |

## Customer data

- Every action is saved to `customer_log.csv` in this folder (date, name, number, model, problem, action).
- AccessViewer does not copy anything from the phone.
- You are storing personal details, so UK GDPR applies: keep the computer password-protected, tell customers what you record, and delete old entries you no longer need.
