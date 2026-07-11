import pyperclip


def set_clipboard(text):
    """
    Copies the given text into the laptop's system clipboard.

    On Arch Linux, pyperclip needs a clipboard backend installed:
      X11:      sudo pacman -S xclip
                (or: sudo pacman -S xsel)
      Wayland:  sudo pacman -S wl-clipboard
    """

    pyperclip.copy(text or "")


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
