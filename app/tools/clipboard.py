import pyperclip
import shutil
import subprocess

def set_clipboard(text):
    """
    Copies the given text into the laptop's system clipboard
    and sends a desktop notification.

    Requires:
      - pyperclip
      - notify-send (libnotify)

    On Arch Linux:
      sudo pacman -S libnotify

    Clipboard backends:
      X11:      sudo pacman -S xclip
      Wayland:  sudo pacman -S wl-clipboard
    """

    content = text or ""

    pyperclip.copy(content)

    if shutil.which("notify-send"):
        subprocess.Popen(
            [
                "notify-send",
                "evo-lab",
                "Clipboard updated from other device!"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

def get_clipboard():
    """
    Reads the current laptop clipboard contents. Returns None if no
    clipboard backend is available rather than raising, so the page
    can still render.
    """

    try:
        return pyperclip.paste()
    except pyperclip.PyperclipException:
        return None
