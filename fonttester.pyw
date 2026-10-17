# fonttester.pyw: a HUD's fonts as Counter-Strike: Source draws them (cssfont.py), and its font blocks edited.
# Left: every font of the HUD's schemes. Middle: the text as the game draws it: typed, a speedometer or jhud, drawn
# once or as many times as the servers' plugins make the game draw it. Right: the picked font's block for this screen
# (every change goes into the app's copy of the HUD's scheme as it's made, Save writes the files; Undo, Restore).
import copy, json, os, random, re, struct, sys, tempfile, time, tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox
import numpy as np
import customtkinter as ctk
from PIL import Image, ImageTk
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cssfont as C

def find_game():
    """The cstrike folder of the CS:S install Steam knows of (in any of its library folders), else None."""
    import winreg
    roots = []
    for hive, key, value in ((winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                             (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')):
        try:
            with winreg.OpenKey(hive, key) as k: roots.append(winreg.QueryValueEx(k, value)[0])
        except OSError: pass
    libs = []
    for root in roots + [r'C:\Program Files (x86)\Steam']:
        libs.append(root)
        try: vdf = open(os.path.join(root, 'steamapps', 'libraryfolders.vdf'), encoding='utf-8', errors='replace').read()
        except OSError: continue
        libs += [m.replace('\\\\', '\\') for m in re.findall(r'"path"\s+"([^"]+)"', vdf)]   # (written with \\ in the file)
    for lib in libs:
        p = os.path.join(lib, 'steamapps', 'common', 'Counter-Strike Source', 'cstrike')
        if os.path.isdir(p): return os.path.realpath(p)            # (its real letter case: Steam keeps it lower-case)
    return None

GAME = find_game()                                             # (cstrike: where a HUD's missing bitmap files come from)
CUSTOM = os.path.join(GAME, 'custom') if GAME else ''          # (no game found: HUDs opened with Open…)
HERE = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
BUNDLE = getattr(sys, '_MEIPASS', HERE)
SETTINGS = os.path.join(os.environ.get('APPDATA') or HERE, 'CSS Font Tester', 'settings.json')
PAK = os.path.join(GAME, 'cstrike_pak_dir.vpk') if GAME else ''

def vanilla_dirs():
    """Where a #base file the HUD hasn't comes from, in the game's order: cstrike's VPK (its schemes copied out to the
    settings folder, again when the game updates), cstrike, hl2, platform. None of it without the game."""
    if not GAME: return []
    root, cache = os.path.dirname(GAME), os.path.join(os.path.dirname(SETTINGS), 'game schemes')
    if os.path.isfile(PAK) and os.path.getmtime(PAK) > (os.path.getmtime(cache) if os.path.isdir(cache) else 0):
        try:
            pak = C.VPK(PAK); os.makedirs(cache, exist_ok=True)
            for f in pak.files:
                if f.startswith('resource/') and f.count('/') == 1 and 'scheme' in f and f.endswith('.res'):
                    open(os.path.join(cache, f[9:]), 'wb').write(pak.read(f))
            os.utime(cache)
        except (OSError, ValueError, KeyError, struct.error): pass
    return [cache, os.path.join(GAME, 'resource'), os.path.join(root, 'hl2', 'resource'), os.path.join(root, 'platform', 'resource')]

SCHEMES = {'Client': 'ClientScheme.res', 'Source': 'SourceScheme.res', 'Chat': 'ChatScheme.res'}
SCREENS = ['1280x720', '1366x768', '1600x900', '1920x1080', '2560x1440', '3840x2160']
SCALES = {'centerprinttext', 'centerspeedtext'}                # one entry the game grows with the screen: kept so
HUDMSG = 'Client: CenterPrintText'                             # the servers' HudMsg texts' font (jhud, records)
# how the servers' plugins send their texts (read 2026-10-11): each send still held is drawn again over the others
HOLD = {'Custom': 2.6,          # shavit-hud's top-left records: sent every 100 ticks (1 s), held 2.6 s
        'Speedometer': 0.2,     # bhop-get-stats' speedometer: sent every 10 ticks, held 0.2 s
        'jhud': 1.0}            # bhop-get-stats' jhud: sent each jump, held 1.0 s
RESEND = 1.0                                                   # (shavit's records)
# bhop-get-stats' colours, its defaults: gain/speed really bad, bad, meh, good, really good
GAIN = [(255, 0, 0), (255, 165, 0), (0, 255, 0), (0, 255, 255), (255, 255, 255)]
JUMP_SPEEDS = [(280, 282, 287, 289), (366, 370, 375, 380), (438, 442, 450, 455), (500, 505, 515, 525), (555, 560, 570, 580),
               (605, 610, 620, 633), (655, 665, 675, 680), (700, 710, 725, 730), (740, 750, 765, 770), (780, 790, 805, 810),
               (810, 820, 840, 850), (850, 860, 875, 885), (880, 900, 900, 920), (910, 920, 935, 955), (945, 955, 965, 990),
               (970, 980, 1000, 1020)]
BACKS = {'Dark grey': (58, 58, 58), 'Black': (0, 0, 0), 'White': (235, 235, 235), 'Sky blue': (140, 160, 185)}
# the maps' own textures, read from the game's VPK when picked: walls and floors tiled at about their size in game,
# skies stretched over the screen
TEXTURES = {'Dust: sand wall': 'de_dust/sitebwall01', 'Dust: old wall': 'de_dust/residwall01', 'Dust: sand': 'de_dust/groundsand03',
            'Dust: crate': 'de_dust/picrate1', 'Dust: sky': 'skybox/sky_dustft', 'Italy: plaster': 'cs_italy/marketwall02',
            'Italy: brick': 'cs_italy/brickwall01', 'Italy: sky': 'skybox/italyft', 'Aztec: stone': 'de_aztec/stonework01',
            'Aztec: grass': 'de_aztec/ground01grass', 'Nuke: concrete': 'de_nuke/nukconcretewalla', 'Nuke: metal wall': 'de_nuke/nukmetwalla',
            'Nuke: metal floor': 'de_nuke/nuke_metalfloor_01', 'Train: block wall': 'de_train/train_brick_wall_01',
            'Train: cement': 'de_train/train_cement_floor_01', 'Office: sky': 'skybox/officeft'}
# the font block's options: key, label, kind (None: a flag)
OPTIONS = [('name', 'Font', 'face'), ('tall', 'Tall', 'int'), ('weight', 'Weight', 'int'), ('antialias', 'Anti-aliasing', None),
           ('dropshadow', 'Drop shadow', None), ('outline', 'Outline', None), ('additive', 'Additive', None), ('italic', 'Italic', None),
           ('underline', 'Underline', None), ('strikeout', 'Strike-out', None), ('rotary', 'Rotary', None), ('symbol', 'Symbol', None),
           ('custom', 'Custom', None), ('bitmap', 'Bitmap', None), ('blur', 'Blur', 'int'), ('scanlines', 'Scan lines', 'int'),
           ('scalex', 'Scale X', 'num'), ('scaley', 'Scale Y', 'num')]
# what each does in the game (in-game shots, 2026-10-12), shown on hover
NOTES = {'name': "The font's name in Windows. One that isn't installed draws as Tahoma",
         'tall': 'Letter height in pixels; the game draws 255 at most',
         'weight': 'Only the weights the font has: Arial draws 400 or 700, Segoe UI 400, 600 or 700 (in between: the nearest)',
         'antialias': 'Smooth edges',
         'dropshadow': 'A black 1-pixel shadow down and right. With Anti-aliasing it only fills fully clear pixels, so it comes '
                       'out patchy. Shows nothing on Additive text',
         'outline': 'A black 1-pixel edge round every letter. Shows nothing on Additive text',
         'additive': "Adds its light to what's behind instead of covering it, so it melts into a bright background. A server "
                     'text sent again while the last is still up is drawn once per copy, and additive copies add up near white',
         'italic': 'Slanted letters; made slanted when the font has no italic',
         'underline': 'A full line only without Anti-aliasing; with it, only a mark in the spaces',
         'strikeout': 'A full line only without Anti-aliasing; with it, a 2-pixel dot in the spaces',
         'rotary': 'A grey line across the middle',
         'symbol': 'Needed by symbol fonts (Marlett, Wingdings): without it they draw as a plain font. On a plain font it '
                   'turns the letters into symbols',
         'custom': 'With Anti-aliasing, also smooths letters past Latin-1 (Ā), but letters outside the Windows character set '
                   '(Cyrillic) turn into boxes',
         'blur': 'A glow round the letters, this many pixels wide',
         'scanlines': 'Every this many rows a darker one (2 or more)',
         'bitmap': 'A picture of letters (.vbf) instead of a Windows font, drawn as made',
         'scalex': 'Bitmap fonts only: how much wider it is drawn', 'scaley': 'Bitmap fonts only: how much taller it is drawn'}
GROWN_NOTES = {'antialias': 'No effect on this font: it grows with the screen, so the game always smooths it',
               'underline': 'Little or no effect on this font: it draws only without Anti-aliasing, which a font that grows '
                            'with the screen always has (only a mark in the spaces)'}
GROWN_NOTES['strikeout'] = GROWN_NOTES['underline']
KEYS = [k for k, _, _ in OPTIONS]
KIND = {k: kind for k, _, kind in OPTIONS}
DEFAULT = {'name': '', 'tall': '0', 'weight': '0', 'blur': '0', 'scanlines': '0', 'scalex': '1', 'scaley': '1'}
STEPS = {'tall': (1, 0, 255), 'weight': (100, 0, 1000), 'blur': (1, 0, None), 'scanlines': (1, 0, None), 'scalex': (1, 0, None), 'scaley': (1, 0, None)}
ZOOMS = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8, 12, 16]

BG, PANEL, RAISED, FIELD, HOVER, LINE, DIVIDER = '#0d0f13', '#15181d', '#1b1f25', '#22272f', '#2c323c', '#2a2f38', '#3b4250'
TEXT, MUTED, ACCENT, ACCENT_HI = '#e6e8ec', '#7f8693', '#8b7cf6', '#9a8df8'
R, RB, H, GAP = 12, 8, 32, 12                                  # panel and button corners, control height, spacing

def on(v):
    """A flag's value: on unless missing or 0."""
    return bool(num(v))

def num(v, d=0):
    try: return int(float(v))
    except (TypeError, ValueError): return d

def write_atomic(path, data):
    """Bytes to a file all at once: written beside it, then put in its place (a crash leaves the old file whole)."""
    tmp = path + '.fonttester-tmp'
    with open(tmp, 'wb') as f: f.write(data)
    os.replace(tmp, path)

def load_settings():
    try:
        with open(SETTINGS, encoding='utf-8') as f: d = json.load(f)
    except (OSError, ValueError): return {}
    return d if isinstance(d, dict) else {}

def save_settings(d):
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        write_atomic(SETTINGS, json.dumps(d, indent=1).encode('utf-8'))
    except OSError: pass                                       # (favourites not kept: nothing else lost)

class frozen:
    """with frozen(widget): Windows doesn't draw it (or what's in it) until the block's done, then draws it all at once."""
    def __init__(self, widget): self.w = widget
    def __enter__(self):
        try:
            import ctypes; self.u = ctypes.windll.user32; self.h = self.w.winfo_id()
            self.u.SendMessageW(self.h, 0x000B, 0, 0)            # WM_SETREDRAW off
        except Exception: self.u = None
    def __exit__(self, *exc):
        try: self.w.update_idletasks()
        except tk.TclError: pass
        if self.u:
            self.u.SendMessageW(self.h, 0x000B, 1, 0)            # on again, then all of it drawn now
            self.u.RedrawWindow(self.h, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100)   # INVALIDATE ERASE ALLCHILDREN UPDATENOW

def dark_window(win):
    """Windows' title bar dark, the window's own colour (Windows 11; older ones keep theirs)."""
    try:
        import ctypes
        hw = ctypes.windll.user32.GetParent(win.winfo_id())
        set_attr = ctypes.windll.dwmapi.DwmSetWindowAttribute
        set_attr(hw, 20, ctypes.byref(ctypes.c_int(1)), 4)                       # immersive dark mode
        set_attr(hw, 35, ctypes.byref(ctypes.c_int(int(BG[5:7] + BG[3:5] + BG[1:3], 16))), 4)   # caption colour
    except Exception: pass

class Dropdown:
    """A dropdown's list: 15 rows at most (the wheel and a scroll bar for more), the current one picked and in view;
    type to jump to a name, Enter picks, Escape or a click elsewhere closes."""
    ROWS = 15
    now = None
    watching = False

    def __init__(self, widget, values, current, pick):
        if Dropdown.now: Dropdown.now.close()
        Dropdown.now, self.pick, self.typed, self.typed_at, self.opener = self, pick, '', 0.0, widget
        self.values = [v for v in values]
        top = self.top = tk.Toplevel(widget.winfo_toplevel(), bg=LINE)   # (not inside the widget: the wheel over it would
                                                                         # scroll a list it's in too)
        if not Dropdown.watching:                               # (a click anywhere in the app outside the list closes it;
            for seq in ('<Button-1>', '<ButtonPress>'):         # plain Tk: CTk forbids it, and has its own <Button-1> there)
                top.bind_all(seq, Dropdown.clicked, add='+')
            Dropdown.watching = True
        top.overrideredirect(True)
        top.attributes('-topmost', True)                        # (above the app: CTk gives the app the focus back after
                                                                # the click that opened it; set before it's placed: after,
                                                                # Tk moves a borderless window to the screen's corner)
        box = tk.Frame(top, bg=RAISED); box.pack(fill='both', expand=True, padx=1, pady=1)
        longest = max([len(v) for v in self.values] + [8])
        self.list = tk.Listbox(box, height=min(self.ROWS, len(self.values)), width=min(42, longest + 2), bg=RAISED, fg=TEXT,
                               selectbackground=ACCENT, selectforeground='#ffffff', activestyle='none', highlightthickness=0,
                               bd=0, font=('Segoe UI', 10), exportselection=False)
        for v in self.values: self.list.insert('end', ' ' + v)
        self.list.pack(side='left', fill='both', expand=True, padx=(4, 0), pady=4)
        if len(self.values) > self.ROWS:
            sb = ctk.CTkScrollbar(box, command=self.list.yview, width=12, fg_color=RAISED, button_color=FIELD, button_hover_color=HOVER)
            sb.pack(side='right', fill='y', padx=(0, 2), pady=4); self.list.configure(yscrollcommand=sb.set)
        if current in self.values:
            i = self.values.index(current); self.list.selection_set(i); self.list.see(i)
        self.list.bind('<Motion>', self.hover)
        self.list.bind('<ButtonRelease-1>', lambda e: self.choose())
        self.list.bind('<Return>', lambda e: self.choose())
        self.list.bind('<Escape>', lambda e: self.close())
        self.list.bind('<Key>', self.type_to)
        top.bind('<FocusOut>', lambda e: top.after(50, self.closed_unless_focused))
        top.update_idletasks()
        w = max(widget.winfo_width(), top.winfo_reqwidth()); h = top.winfo_reqheight()
        x, y = widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height() + 4
        if y + h > widget.winfo_screenheight() + widget.winfo_vrooty(): y = widget.winfo_rooty() - h - 4   # (no room below: above)
        top.geometry(f'{w}x{h}+{x}+{y}')
        try:                                                    # (Windows 11: rounded corners)
            import ctypes
            ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.windll.user32.GetParent(top.winfo_id()), 33, ctypes.byref(ctypes.c_int(2)), 4)
        except Exception: pass
        top.after(1, self.take_focus)

    def take_focus(self):
        try: self.top.lift(); self.top.focus_force(); self.list.focus_set()
        except tk.TclError: pass

    def hover(self, e):
        i = self.list.nearest(e.y)
        self.list.selection_clear(0, 'end'); self.list.selection_set(i)

    def type_to(self, e):
        if not e.char or not e.char.isprintable(): return
        now = time.monotonic()
        self.typed = (self.typed if now - self.typed_at < 0.8 else '') + e.char.lower(); self.typed_at = now
        for i, v in enumerate(self.values):
            if v.lower().startswith(self.typed):
                self.list.selection_clear(0, 'end'); self.list.selection_set(i); self.list.see(i); break

    def choose(self):
        sel = self.list.curselection()
        if not sel or self.values[sel[0]].startswith('─'): return    # (a separator: nothing)
        v = self.values[sel[0]]
        self.close(); self.pick(v)

    def closed_unless_focused(self):
        if Dropdown.now is not self: return
        try:
            if self.top.focus_get() is None: self.close()       # (focus gone to another program)
        except (KeyError, tk.TclError): self.close()

    @staticmethod
    def clicked(e):
        d = Dropdown.now
        if not d: return
        try:
            w = e.widget
            o = str(d.opener)
            if isinstance(w, str) or w.winfo_toplevel() is d.top or str(w) == o or str(w).startswith(o + '.'): return   # (its own)
        except (KeyError, tk.TclError, AttributeError): pass
        d.close()

    def close(self):
        if Dropdown.now is self: Dropdown.now = None
        try: self.top.destroy()
        except tk.TclError: pass

class Tip:
    """A note by the pointer after a moment over a widget; text() gives it then (it can depend on the font picked)."""
    def __init__(self, widget, text):
        self.widget, self.text, self.top, self.timer = widget, text, None, None
        for seq, f in (('<Enter>', self.wait), ('<Leave>', self.hide), ('<ButtonPress-1>', self.hide)): widget.bind(seq, f, add='+')

    def wait(self, e=None):
        self.hide(); self.timer = self.widget.after(500, self.show)

    def show(self):
        self.timer, t = None, self.text()
        if not t: return
        top = self.top = tk.Toplevel(self.widget, bg=LINE)
        top.overrideredirect(True); top.attributes('-topmost', True)
        tk.Label(top, text=t, bg=RAISED, fg=TEXT, font=('Segoe UI', 9), wraplength=320, justify='left', padx=8, pady=6).pack(padx=1, pady=1)
        top.geometry(f'+{self.widget.winfo_pointerx() + 14}+{self.widget.winfo_pointery() + 18}')

    def hide(self, e=None):
        if self.timer: self.widget.after_cancel(self.timer); self.timer = None
        if self.top: self.top.destroy(); self.top = None

def open_or_close(widget):
    """A dropdown's button: opens its list, or closes it when it's open already."""
    if Dropdown.now and Dropdown.now.opener is widget: Dropdown.now.close(); return True

class Combo(ctk.CTkComboBox):
    def _open_dropdown_menu(self):
        if open_or_close(self): return
        Dropdown(self, list(self.cget('values')), self.get(), self._dropdown_callback)

class Choice(ctk.CTkOptionMenu):
    def _open_dropdown_menu(self):
        if open_or_close(self): return
        Dropdown(self, list(self.cget('values')), self.get(), self._dropdown_callback)

class Ui:
    """The widgets, all one size and look."""
    def __init__(self):
        self.body = ctk.CTkFont(family='Segoe UI', size=13)
        self.small = ctk.CTkFont(family='Segoe UI', size=12)
        self.title = ctk.CTkFont(family='Segoe UI Semibold', size=20)

    def panel(self, parent, colour=PANEL):
        return ctk.CTkFrame(parent, fg_color=colour, corner_radius=R)

    def button(self, parent, text, command, accent=False, width=0):
        return ctk.CTkButton(parent, text=text, command=command, height=H, width=width, corner_radius=RB, font=self.body,
                             fg_color=ACCENT if accent else FIELD, hover_color=ACCENT_HI if accent else HOVER,
                             text_color='#ffffff' if accent else TEXT)

    def entry(self, parent, var, width=0, placeholder=None):
        return ctk.CTkEntry(parent, textvariable=var, width=width, height=H, corner_radius=RB, border_width=0, font=self.body,
                            fg_color=FIELD, text_color=TEXT, placeholder_text=placeholder, placeholder_text_color=MUTED)

    def menu(self, parent, values, var, command=None, width=0):
        return Choice(parent, values=values, variable=var, command=command, width=width, height=H, corner_radius=RB,
                                 font=self.body, dropdown_font=self.body, fg_color=FIELD, button_color=FIELD,
                                 button_hover_color=HOVER, text_color=TEXT, dropdown_fg_color=RAISED,
                                 dropdown_hover_color=HOVER, dropdown_text_color=TEXT, dynamic_resizing=False)

    def combo(self, parent, values, var, command=None, width=0):
        return Combo(parent, values=values, variable=var, command=command, width=width, height=H, corner_radius=RB,
                               border_width=0, font=self.body, dropdown_font=self.body, fg_color=FIELD, button_color=FIELD,
                               button_hover_color=HOVER, text_color=TEXT, text_color_disabled=MUTED, dropdown_fg_color=RAISED,
                               dropdown_hover_color=HOVER, dropdown_text_color=TEXT)

    def check(self, parent, var, command=None):
        return ctk.CTkCheckBox(parent, text='', variable=var, command=command, width=22, height=H, checkbox_width=18,
                               checkbox_height=18, corner_radius=5, border_width=2, fg_color=ACCENT, hover_color=ACCENT_HI,
                               border_color=LINE)

    def segments(self, parent, values, var, command, width):
        return ctk.CTkSegmentedButton(parent, values=values, variable=var, command=command, height=H, width=width, corner_radius=RB,
                                      font=self.body, fg_color=FIELD, selected_color=ACCENT, selected_hover_color=ACCENT_HI,
                                      unselected_color=FIELD, unselected_hover_color=HOVER, text_color=TEXT,
                                      dynamic_resizing=False)

    def label(self, parent, text='', muted=False, font=None, **kw):
        return ctk.CTkLabel(parent, text=text, font=font or (self.small if muted else self.body),
                            text_color=MUTED if muted else TEXT, anchor='w', **kw)

    def stepper(self, parent, var, step=1, lo=0, hi=None, width=170):
        """A number field with − and + either side, step a click (whole numbers, or as typed: 0.5 + 1 is 1.5)."""
        box = ctk.CTkFrame(parent, fg_color='transparent', width=width, height=H)
        def move(d):
            try: v = float(var.get())
            except ValueError: v = 0.0
            v = max(lo, v + d * step) if hi is None else max(lo, min(hi, v + d * step))
            var.set(f'{v:g}')
        box.minus = self.button(box, '−', lambda: move(-1), width=H)
        box.entry = self.entry(box, var, width=width - 2 * H - 12)
        box.plus = self.button(box, '+', lambda: move(1), width=H)
        box.minus.pack(side='left'); box.entry.pack(side='left', padx=6); box.plus.pack(side='left')
        return box

    def swatch(self, parent, rgb, command):
        c = '#%02x%02x%02x' % tuple(rgb)
        return ctk.CTkButton(parent, text='', command=command, width=H, height=H, corner_radius=RB, fg_color=c,
                             hover_color=c, border_width=2, border_color=LINE)

class App:
    def __init__(self, root):
        self.root = root
        root.title('Font Tester')
        self.vanilla = vanilla_dirs()
        self.ui = Ui()
        # the HUD's scheme files: the app's copy, as last read or saved, and as first read (Restore)
        self.texts, self.disk, self.stamps, self.original, self.undo, self.conflicts = {}, {}, {}, {}, [], set()
        self.schemes, self.scheme_files, self.bitmaps, self.faces, self.font_files = {}, {}, {}, [], []
        self.made, self.made_names = {}, []                    # bitmap fonts made here this run
        self.opts, self.start_opts, self.face_before = {}, {}, {}   # the right side's options, per font and screen
        self.cache, self.errors, self.back_cache, self.tmp = {}, {}, {}, None
        favs = load_settings().get('favourites', [])
        self.favs = [f for f in favs if isinstance(f, str)] if isinstance(favs, list) else []
        huds = self.hud_names()
        last = load_settings().get('hud')                      # (the HUD open last, else the first there)
        self.hud = last if isinstance(last, str) and os.path.isdir(os.path.join(last, 'resource')) else \
            os.path.join(CUSTOM, huds[0]) if huds else CUSTOM
        self.active, self.loading, self.bgimg = None, False, None
        self.mode, self.draw_kind = tk.StringVar(value='Custom'), tk.StringVar(value='Draw once')
        self.text, self.colour = tk.StringVar(value='Speed: 1284 u/s   WR: 17.707'), (255, 255, 255)
        self.every, self.screen, self.back = tk.StringVar(value='100'), tk.StringVar(value='2560x1440'), tk.StringVar(value='Dark grey')
        self.sends, self.speed, self.speed_colour, self.jump = [], 1284, GAIN[3], 0
        self.jtext, self.jcolour = '2: 384 (85%)\n79.23', GAIN[4]
        self.centre, self.zoom, self.recentre, self.scene, self.drag = [1280.0, 720.0], 1.0, True, None, None
        self.timers = {}
        self.build()
        self.load()
        self.restart()
        self.watch()

    # ---- layout ----------------------------------------------------------------------------------------------------
    def build(self):
        r, ui = self.root, self.ui
        r.columnconfigure(1, weight=1); r.rowconfigure(0, weight=1)
        # left: the HUD and its fonts
        left = ui.panel(r); left.grid(row=0, column=0, sticky='nsew', padx=(GAP, 0), pady=GAP)
        left.configure(width=290); left.grid_propagate(False); left.columnconfigure(0, weight=1); left.rowconfigure(2, weight=1)
        self.hudvar = tk.StringVar(value=os.path.basename(self.hud) or 'No HUD open')
        bar = ctk.CTkFrame(left, fg_color='transparent'); bar.grid(row=0, column=0, sticky='ew', padx=GAP, pady=(GAP, 8))
        bar.columnconfigure(0, weight=1)
        ctk.CTkLabel(bar, textvariable=self.hudvar, height=H, corner_radius=RB, fg_color=FIELD, text_color=TEXT, font=ui.body,
                     anchor='w', padx=12).grid(row=0, column=0, sticky='ew')
        ui.button(bar, 'Open…', self.open_hud, width=80).grid(row=0, column=1, padx=(8, 0))
        self.search_entry = ui.entry(left, None, placeholder='Search')
        self.search_entry.grid(row=1, column=0, sticky='ew', padx=GAP, pady=(0, 8))
        self.search_entry.bind('<KeyRelease>', lambda e: self.fill_tree())
        box = ui.panel(left, RAISED); box.grid(row=2, column=0, sticky='nsew', padx=GAP, pady=(0, GAP))
        box.rowconfigure(0, weight=1); box.columnconfigure(0, weight=1)
        st = ttk.Style(r); st.theme_use('clam')
        st.configure('Fonts.Treeview', background=RAISED, fieldbackground=RAISED, foreground=TEXT, borderwidth=0,
                     rowheight=28, font=('Segoe UI', 10), indent=14)
        st.map('Fonts.Treeview', background=[('selected', ACCENT)], foreground=[('selected', '#ffffff')])
        st.layout('Fonts.Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
        st.configure('Fonts.Treeview.Item', indicatorsize=0)
        self.tree = ttk.Treeview(box, show='tree', selectmode='extended', style='Fonts.Treeview')
        self.tree.grid(row=0, column=0, sticky='nsew', padx=(6, 0), pady=6)
        sb = ctk.CTkScrollbar(box, command=self.tree.yview, width=12, fg_color=RAISED, button_color=FIELD, button_hover_color=HOVER)
        sb.grid(row=0, column=1, sticky='ns', padx=(0, 4), pady=6)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure('group', foreground=MUTED, font=('Segoe UI Semibold', 9))
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.picked())
        self.tree.bind('<Button-3>', self.tree_menu)
        # middle: the preview
        mid = ui.panel(r); mid.grid(row=0, column=1, sticky='nsew', padx=GAP, pady=GAP)
        mid.columnconfigure(0, weight=1); mid.rowconfigure(1, weight=1)
        top = ctk.CTkFrame(mid, fg_color='transparent'); top.grid(row=0, column=0, sticky='ew', padx=GAP, pady=(GAP, 8))
        top.columnconfigure(1, weight=1)
        ui.segments(top, ['Custom', 'Speedometer', 'jhud'], self.mode, lambda v: self.restart(recentre=True), 330).grid(row=0, column=0, sticky='w')
        ui.segments(top, ['Draw once', 'Real to game'], self.draw_kind, lambda v: self.restart(), 250).grid(row=0, column=2, sticky='e')
        view = ui.panel(mid, BG); view.grid(row=1, column=0, sticky='nsew', padx=GAP)
        view.rowconfigure(0, weight=1); view.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(view, bg=BG, highlightthickness=0, bd=0, cursor='fleur')
        self.canvas.grid(row=0, column=0, sticky='nsew', padx=R // 2, pady=R // 2)
        self.picture = self.canvas.create_image(0, 0, anchor='nw')
        self.canvas.bind('<Configure>', lambda e: self.show())
        self.canvas.bind('<MouseWheel>', self.wheel)
        self.canvas.bind('<ButtonPress-1>', self.grab_view)
        self.canvas.bind('<B1-Motion>', self.move_view)
        self.canvas.bind('<Double-Button-1>', lambda e: self.reset_view())
        bar = ctk.CTkFrame(mid, fg_color='transparent'); bar.grid(row=2, column=0, sticky='ew', padx=GAP, pady=GAP)
        bar.columnconfigure(0, weight=1)
        self.text_entry = ui.entry(bar, self.text, placeholder='Text'); self.text.trace_add('write', lambda *_: self.later())
        self.every_box = ctk.CTkFrame(bar, fg_color='transparent')
        ui.label(self.every_box, 'Every').pack(side='left', padx=(2, 8))
        ui.entry(self.every_box, self.every, width=72).pack(side='left')
        ui.label(self.every_box, 'ms', muted=True).pack(side='left', padx=8)
        self.every.trace_add('write', lambda *_: self.later(self.restart, 300))
        self.colour_button = ui.swatch(bar, self.colour, self.pick_colour)
        self.colour_button.grid(row=0, column=1, padx=(8, 0))
        values = list(BACKS) + (list(TEXTURES) if os.path.isfile(PAK) else []) + ['Picture…']
        ui.menu(bar, values, self.back, self.pick_back, width=180).grid(row=0, column=2, padx=(8, 0))
        self.zoom_label = ui.label(bar, '100%', muted=True, width=52); self.zoom_label.configure(anchor='e')
        self.zoom_label.grid(row=0, column=3, padx=(8, 2))
        # right: the picked font's block for this screen
        right = ui.panel(r); right.grid(row=0, column=2, sticky='nsew', padx=(0, GAP), pady=GAP)
        right.configure(width=360); right.grid_propagate(False); right.columnconfigure(0, weight=1); right.rowconfigure(3, weight=1)
        # Options or Raw: centred at the top, like the preview's toggles
        self.raw, self.side_view = tk.BooleanVar(value=False), tk.StringVar(value='Options')
        ui.segments(right, ['Options', 'Raw'], self.side_view, lambda v: (self.raw.set(v == 'Raw'), self.toggle_raw()), 220).grid(
            row=0, column=0, pady=(GAP, 0))
        head = ctk.CTkFrame(right, fg_color='transparent'); head.grid(row=1, column=0, sticky='ew', padx=16, pady=(10, 0))
        head.columnconfigure(0, weight=1)
        self.name_label = ui.label(head, 'Pick a font', font=ui.title); self.name_label.grid(row=0, column=0, sticky='w')
        self.scheme_label = ui.label(head, '', muted=True); self.scheme_label.grid(row=1, column=0, sticky='w')
        res = ctk.CTkFrame(right, fg_color='transparent'); res.grid(row=2, column=0, sticky='ew', padx=16, pady=(10, 8))
        res.columnconfigure(1, weight=1)
        ui.combo(res, SCREENS, self.screen, None, width=140).grid(row=0, column=0, sticky='w')
        self.screen.trace_add('write', lambda *_: self.later(self.screen_changed, 300))
        self.yres_label = ui.label(res, '', muted=True); self.yres_label.grid(row=0, column=1, sticky='w', padx=(10, 0))
        holder = ctk.CTkFrame(right, fg_color='transparent'); holder.grid(row=3, column=0, sticky='nsew', padx=GAP)
        lst = ctk.CTkScrollableFrame(holder, fg_color=RAISED, corner_radius=R, scrollbar_button_color=FIELD,
                                     scrollbar_button_hover_color=HOVER)
        lst.pack(fill='both', expand=True)                     # (in a frame of its own: it hides as one with Raw)
        lst.columnconfigure(0, weight=1)
        self.options_list = lst
        self.values, self.value_widgets, self.flags, self.key_labels = {}, {}, {}, {}
        self.rows = {}
        for k, label, kind in OPTIONS:
            row = self.rows[k] = ctk.CTkFrame(lst, fg_color='transparent', corner_radius=RB)
            row.columnconfigure(2, weight=1)
            self.key_labels[k] = ui.label(row, label); self.key_labels[k].grid(row=0, column=2, sticky='ew', padx=(14, 0), pady=4)
            Tip(self.key_labels[k], lambda k=k: self.note(k))
            for w in (row, self.key_labels[k]):                # (dragged by anything but a button or a field)
                w.bind('<ButtonPress-1>', lambda e, k=k: self.drag_start(k, e))
                w.bind('<B1-Motion>', self.drag_move)
                w.bind('<ButtonRelease-1>', self.drag_end)
            if kind is None:
                self.flags[k] = tk.BooleanVar()
                self.value_widgets[k] = ui.check(row, self.flags[k], lambda k=k: self.flagged(k))
                self.value_widgets[k].grid(row=0, column=3, sticky='e', padx=(4, 10), pady=2)
            else:
                self.values[k] = tk.StringVar()
                w = (ui.combo(row, [], self.values[k], lambda v, k=k: self.valued(k), width=170) if kind == 'face'
                     else ui.stepper(row, self.values[k], *STEPS[k]))
                w.grid(row=0, column=3, sticky='e', padx=(4, 8), pady=2)
                self.values[k].trace_add('write', lambda *_, k=k: self.valued(k))
                self.value_widgets[k] = w
        self.divider = ctk.CTkFrame(lst, fg_color=DIVIDER, height=2, corner_radius=1)   # (in the block / not)
        self.drag_room = ctk.CTkFrame(lst, fg_color='transparent', height=1)  # (holds the rows' place while they move)
        self.dragging = None
        acts = ctk.CTkFrame(right, fg_color='transparent'); acts.grid(row=4, column=0, sticky='ew', padx=GAP, pady=(GAP, 0))
        for c in range(6): acts.columnconfigure(c, weight=1, uniform='acts')
        ui.button(acts, 'Add font to HUD', self.add_font_to_hud).grid(row=0, column=0, columnspan=6, sticky='ew')
        ui.button(acts, 'Undo', self.undo_last).grid(row=1, column=0, columnspan=2, sticky='ew', padx=(0, 4), pady=(8, 0))
        ui.button(acts, 'Restore', self.restore).grid(row=1, column=2, columnspan=2, sticky='ew', padx=4, pady=(8, 0))
        self.save_button = ui.button(acts, 'Save', self.save, accent=True)
        self.save_button.grid(row=1, column=4, columnspan=2, sticky='ew', padx=(4, 0), pady=(8, 0))
        self.maker_button = ui.button(right, 'Create bitmap font', self.open_maker)
        self.maker_button.grid(row=5, column=0, sticky='ew', padx=GAP, pady=GAP)
        # Raw: the font's block as the file has it, in place of everything under the name
        self.raw_box = ctk.CTkTextbox(right, font=ctk.CTkFont(family='Consolas', size=12), fg_color=RAISED, text_color=TEXT,
                                      corner_radius=R, wrap='none', border_width=0, scrollbar_button_color=FIELD,
                                      scrollbar_button_hover_color=HOVER)
        import tkinter.font as tkfont
        self.raw_box._textbox.configure(tabs=(tkfont.Font(family='Consolas', size=12).measure('  '),))   # (a short indent a level)
        self.status = ctk.CTkLabel(view, text='', font=ui.small, text_color=TEXT, fg_color=RAISED, corner_radius=RB, height=28)

    def hud_names(self):
        return sorted(d for d in os.listdir(CUSTOM) if os.path.isdir(os.path.join(CUSTOM, d, 'resource'))) if os.path.isdir(CUSTOM) else []

    def flash(self, text, ms=6000):
        """A message over the preview's bottom left, for a while."""
        if self.timers.get('flash'): self.root.after_cancel(self.timers['flash'])
        self.status.configure(text=f'  {text}  '); self.status.place(x=R, rely=1.0, y=-R, anchor='sw')
        self.timers['flash'] = self.root.after(ms, self.status.place_forget)

    def later(self, fn=None, ms=30):
        """fn once, ms after the last call for it; the drawing (no fn) once, ms after the first: what changes faster
        than it draws (a 1 ms speedometer) still gets drawn."""
        if fn is None:
            if not self.timers.get('render'): self.timers['render'] = self.root.after(ms, self.render)
            return
        if self.timers.get(fn.__name__): self.root.after_cancel(self.timers[fn.__name__])
        self.timers[fn.__name__] = self.root.after(ms, fn)

    def tmp_dir(self):
        if not self.tmp: self.tmp = tempfile.mkdtemp(prefix='fonttester')
        return self.tmp

    # ---- the HUD's files ---------------------------------------------------------------------------------------------
    def open_hud(self):
        """Another HUD: its folder (the one with resource in it; the resource folder itself will do too)."""
        if not self.confirm_discard(): return
        d = filedialog.askdirectory(initialdir=self.hud or CUSTOM or None, title='Pick a HUD folder')
        if not d: return
        d = os.path.normpath(d)
        if os.path.basename(d).lower() == 'resource': d = os.path.dirname(d)
        if not os.path.isdir(os.path.join(d, 'resource')): self.flash('That folder has no resource folder: not a HUD'); return
        self.pick_hud(d)

    def pick_hud(self, path):
        self.hud = path
        self.hudvar.set(os.path.basename(self.hud))
        self.texts, self.disk, self.stamps, self.undo, self.opts, self.start_opts = {}, {}, {}, [], {}, {}
        self.conflicts = set()
        self.made, self.made_names, self.face_before, self.active = {}, [], {}, None
        self.load(); self.restart(recentre=True)

    def inside(self, p):
        return os.path.normcase(os.path.abspath(p)).startswith(os.path.normcase(os.path.abspath(self.hud)) + os.sep)

    def read(self, p):
        """A scheme file's text: the app's copy of a HUD file (made on first read), else the file (a #base outside)."""
        if p in self.texts: return self.texts[p]
        with open(p, 'rb') as f: t = f.read().decode('latin-1')     # (latin-1: every byte kept as it was)
        if self.inside(p): self.texts[p] = self.disk[p] = t; self.stamps[p] = self.mtime(p)
        return t

    def mtime(self, p):
        return os.path.getmtime(p) if os.path.isfile(p) else 0

    def load(self):
        """The HUD's schemes (with their #base files), from the app's copies, its font files loaded."""
        self.schemes, self.scheme_files, self.font_files = {}, {}, []
        for short, name in (SCHEMES.items() if self.hud else ()):   # (no HUD open: not one from the working folder)
            p = os.path.join(self.hud, 'resource', name)
            if not os.path.isfile(p): continue
            items, files = C.load_scheme(p, self.vanilla, self.read)
            self.schemes[short], self.scheme_files[short] = items, files
            self.font_files += C.custom_font_files(items, self.hud)
        C.load_font_files(self.font_files)
        self.original.setdefault(self.hud, dict(self.texts))  # (as the app first read them: Restore)
        self.bitmaps = C.bitmap_font_files(self.schemes.values(), [self.hud] + ([GAME] if GAME else []))
        for p in self.font_files + [p for pair in self.bitmaps.values() for p in pair]: self.stamps.setdefault(p, self.mtime(p))
        for f in self.cache.values(): f.close()
        self.cache, self.errors = {}, {}
        used = sorted({v for items in self.schemes.values() for _, e in (C.find(items, 'Fonts') or [])
                       if isinstance(e, list) for _, d in e if isinstance(d, list) for k, v in d if k.lower() == 'name'}, key=str.lower)
        self.faces = used + C.faces()
        self.fill_tree()
        if not self.tree.selection():                          # (the fonts picked last in this HUD; the first time, none)
            st = load_settings()
            last = st.get('selection', []) if st.get('hud') == self.hud else []
            if not isinstance(last, list): last = []
            sel = [i for i in last if isinstance(i, str) and self.tree.exists(i)]
            if sel:
                self.tree.selection_set(sel); self.tree.see(sel[-1])
                if not self.active and st.get('active') in sel: self.active = st['active']
        self.set_active(self.active if self.active and self.tree.exists(self.active) else (list(self.tree.selection()) or [None])[-1])
        self.saved_state()

    def watch(self):
        """A HUD or font file changed on disk: read again (the app's copy kept if it has changes not saved; Save then
        asks before writing over the outside change)."""
        self.timers['watch'] = self.root.after(500, self.watch)  # (first: an error below doesn't end the watching)
        changed = False
        for p in list(self.stamps):
            try:
                m = self.mtime(p)
                if m == self.stamps[p]: continue
                t = None
                if p in self.texts and m:
                    with open(p, 'rb') as f: t = f.read().decode('latin-1')
            except OSError: continue                            # (being written, or locked: tried again next time)
            self.stamps[p] = m; changed = True
            if t is None: continue
            if self.texts[p] == self.disk[p]:
                self.texts[p] = t                               # (the app's edits were based on the old text: dropped)
                self.undo = [u for u in self.undo if p not in u[1]]
                self.opts, self.start_opts = {}, {}
            else:
                self.conflicts.add(p)
                self.flash(f'{os.path.basename(p)} changed on disk; your unsaved changes are kept')
            self.disk[p] = t
        if changed:
            try: self.reload()
            except Exception as ex: self.flash(f'Could not read the HUD: {ex}')

    def reload(self):
        self.load(); self.later()

    def change(self, label, texts, created=()):
        """The app's copies changed (undoable): {path: new text}; created: files made, deleted again by Undo."""
        texts = {p: t for p, t in texts.items() if t != self.texts[p]}
        if not texts and not created: return False
        self.undo.append((label, {p: self.texts[p] for p in texts}, list(created)))
        self.texts.update(texts)
        self.reload()
        return True

    def saved_state(self):
        unsaved = any(self.texts[p] != self.disk[p] for p in self.texts)
        self.save_button.configure(text='Save  •' if unsaved else 'Save')

    def unsaved(self):
        return [p for p in self.texts if self.texts[p] != self.disk[p]]

    def save(self):
        self.flush()
        out = self.unsaved()
        if not out: self.flash('Nothing to save'); return True
        clash = [p for p in out if p in self.conflicts or self.mtime(p) != self.stamps.get(p)]
        if clash and not messagebox.askyesno('Save', ', '.join(os.path.basename(p) for p in clash) + ' changed on disk since '
                                             'it was read here. Save over those changes?', parent=self.root): return False
        try: data = {p: self.texts[p].encode('latin-1') for p in out}   # (all checked before anything is written)
        except UnicodeEncodeError as ex:
            self.flash(f'Not saved: "{ex.object[ex.start:ex.end]}" is not allowed in a scheme file (Latin-1 only)'); return False
        for p in out:
            try: write_atomic(p, data[p])
            except OSError as ex: self.flash(f'Not saved: {os.path.basename(p)}: {ex.strerror}'); self.saved_state(); return False
            self.disk[p] = self.texts[p]; self.stamps[p] = self.mtime(p); self.conflicts.discard(p)
        self.undo = [(label, texts, []) for label, texts, _ in self.undo]   # (made files now in saved files: kept on Undo)
        self.saved_state()
        self.flash('Saved ' + ', '.join(os.path.basename(p) for p in out))
        return True

    def confirm_discard(self):
        """Unsaved changes: save them, drop them, or stay (False)."""
        self.flush()
        if not self.unsaved(): return True
        a = messagebox.askyesnocancel('Unsaved changes', 'Save your changes to ' + os.path.basename(self.hud) + ' first?', parent=self.root)
        if a is None: return False
        return self.save() if a else True

    def undo_last(self):
        self.flush()
        if not self.undo: self.flash('Nothing to undo'); return
        label, texts, created = self.undo.pop()
        self.texts.update(texts)
        for p in created:
            if os.path.isfile(p): os.remove(p)
        self.made = {k: v for k, v in self.made.items() if os.path.isfile(v[0])}
        self.made_names = [n for n in self.made_names if n.lower() in self.made]
        self.opts, self.start_opts = {}, {}
        self.reload(); self.flash(f'Undone: {label}')

    def restore(self):
        """The font blocks as they were when the app opened (undoable; Save writes them)."""
        self.flush()
        first = self.original.get(self.hud, {})
        self.opts, self.start_opts = {}, {}
        if self.change('restore', {p: t for p, t in first.items() if p in self.texts}): self.flash('As when opened: Save to write it')
        else: self.reload(); self.flash('Already as when opened')

    # ---- the fonts list ----------------------------------------------------------------------------------------------
    def fill_tree(self):
        keep, q = set(self.tree.selection()), self.search_entry.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        have = {f'{s}: {f}' for s, items in self.schemes.items() for f, _ in (C.find(items, 'Fonts') or [])}
        favs = [i for i in self.favs if i in have and q in i.split(': ', 1)[1].lower()]
        if favs:                                               # favourites first, out of their scheme's list
            self.tree.insert('', 'end', iid='★', text='FAVOURITES', open=True, tags=('group',))
            for iid in favs: self.tree.insert('★', 'end', iid=iid, text=self.label(iid))
        for short, items in self.schemes.items():
            fonts = [f for f, _ in (C.find(items, 'Fonts') or []) if q in f.lower() and f'{short}: {f}' not in self.favs]
            if not fonts: continue
            self.tree.insert('', 'end', iid=short, text=f'{short.upper()}SCHEME', open=True, tags=('group',))
            for font in fonts:
                iid = f'{short}: {font}'
                if not self.tree.exists(iid): self.tree.insert(short, 'end', iid=iid, text=self.label(iid))
        sel = [i for i in keep if self.tree.exists(i)]
        if sel: self.tree.selection_set(sel)

    def label(self, iid):
        short, font = iid.split(': ', 1)
        key = (iid, self.h())
        edited = key in self.opts and self.opts[key] != self.start_opts.get(key)
        return ('●  ' if edited else '') + font + (f'   {short}' if iid in self.favs else '')

    def tree_menu(self, e):
        iid = self.tree.identify_row(e.y)
        if ': ' not in iid: return
        if not getattr(self, 'fav_menu', None):                # (one menu, its line set each time)
            self.fav_menu = tk.Menu(self.root, tearoff=0, bg=RAISED, fg=TEXT, activebackground=ACCENT, activeforeground='#ffffff',
                                    bd=0, font=('Segoe UI', 10))
        m = self.fav_menu; m.delete(0, 'end')
        m.add_command(label='Remove from favourites' if iid in self.favs else 'Add to favourites', command=lambda: self.favourite(iid))
        m.tk_popup(e.x_root, e.y_root)

    def favourite(self, iid):
        if iid in self.favs: self.favs.remove(iid)
        else: self.favs.append(iid)
        save_settings({**load_settings(), 'favourites': self.favs})
        self.fill_tree()
        if self.tree.exists(iid): self.tree.see(iid)

    def picked(self):
        if getattr(self, 'pending', None): self.flush()
        sel = [i for i in self.tree.selection() if ': ' in i]
        now = (self.hud, tuple(sel), self.tree.focus())
        if sel and now == getattr(self, 'last_pick', None): return
        self.last_pick = now
        if sel:
            focus = self.tree.focus()
            self.set_active(focus if focus in sel else sel[-1])
            save_settings({**load_settings(), 'hud': self.hud, 'selection': sel, 'active': self.active})   # (for next time)
        self.restart()

    # ---- the picked font's block -------------------------------------------------------------------------------------
    def h(self):
        return num(self.screen.get().lower().split('x')[-1], 1080)

    def screen_size(self):
        try: w, h = (int(v) for v in self.screen.get().lower().split('x'))
        except ValueError: return None
        return (w, h) if 100 <= w <= 10000 and 100 <= h <= 10000 else None

    def screen_changed(self):
        if not self.screen_size(): return
        self.flush()
        self.set_active(self.active); self.fill_tree(); self.restart(recentre=True)

    def scales(self, iid):
        return iid.split(': ', 1)[1].lower() in SCALES

    def note(self, k):
        """The hover note for an option; on a font that grows with the screen, with its sizes in px here."""
        if not self.active: return NOTES[k]
        o, h = self.state(self.active), self.h()
        if not (self.scales(self.active) and not on(o['bitmap']) and not C.yres_range(self.current(self.active))):
            return NOTES[k]
        if k in GROWN_NOTES: return GROWN_NOTES[k]
        n = int(num(self.values[k].get())) if k in ('tall', 'blur', 'scanlines') else 0
        px = int(h / 480 * n)
        if k == 'tall': return f'Letter height: it grows with the screen ({n} is {min(px, 255)} px at {h}p; the game draws 255 at most)'
        if k == 'blur': return f'A glow, this many units wide: it grows with the screen ({n} is {px} px at {h}p)'
        if k == 'scanlines': return f'{NOTES[k]}: it grows with the screen ({n} is every {px} px at {h}p)'
        return NOTES[k]

    def entries(self, iid):
        short, font = iid.split(': ', 1)
        return C.font_entries(self.schemes.get(short, []), font)

    def current(self, iid):
        """The entry the game uses now at this screen (dict), or {}."""
        h = self.h()
        for _, d in self.entries(iid):
            r = C.yres_range(d)
            if not r or r[0] <= h <= r[1]: return d
        return {}

    def state(self, iid):
        """The right side's options for a font at this screen: {key: value, or None: the block hasn't it}, '_extra': other keys.
        From the entry the game uses now; a grown one going where it won't grow gets its sizes in px (looks the same)."""
        key = (iid, self.h())
        if key not in self.opts:
            cur = self.current(iid)
            o = {k: (('1' if num(cur[k]) else '0') if KIND[k] is None else cur[k]) if k in cur else None for k in KEYS}
            o['_extra'] = {k: v for k, v in cur.items() if k not in KEYS and k != 'yres'}
            o['_order'] = [k for k in cur if k != 'yres']        # (the order the block's lines are in, and are written in)
            if cur and not C.yres_range(cur) and not (self.scales(iid) and not on(o['bitmap'])):
                d = C.sized(cur, self.h(), True)
                for k, v in (('tall', d[1]), ('blur', d[2]), ('scanlines', d[3]), ('scalex', d[4]), ('scaley', d[5])):
                    if o[k] is not None: o[k] = f'{v:g}' if isinstance(v, float) else str(v)
                if num(d[0].get('antialias')): o['antialias'] = '1'          # (grown: the game turned it on)
            self.opts[key], self.start_opts[key] = o, copy.deepcopy(o)
        return self.opts[key]

    def target(self, iid):
        """Where a change to this font goes: (key, yres, the entry it goes before, the entry)."""
        o = self.state(iid)
        key, yres, before = C.place(self.entries(iid), self.h(), self.scales(iid))
        if self.scales(iid): yres = '1 9999' if on(o['bitmap']) else None  # (a bitmap font isn't grown: drawn as made)
        d = {k: o[k] if k in KEYS else o['_extra'][k] for k in self.present(o) + [k for k in o['_order'] if k in o['_extra']]}
        d = {k: d[k] for k in sorted(d, key=lambda k: o['_order'].index(k) if k in o['_order'] else len(o['_order']))}
        if yres: d['yres'] = yres
        return key, yres, before, d

    def set_active(self, iid, resort=True):
        self.active = iid if iid and ': ' in iid else None
        if not self.active:
            self.name_label.configure(text='Pick a font'); self.scheme_label.configure(text=''); self.yres_label.configure(text='')
            self.raw_box.configure(state='normal'); self.raw_box.delete('1.0', 'end'); self.raw_box.configure(state='disabled')
            return
        short, font = self.active.split(': ', 1)
        o = self.state(self.active)
        self.loading = True
        try:
            if resort: self.sort_rows(o)                       # (not while editing: no row moves under the pointer)
            looks = getattr(self, 'row_looks', {})              # (only what changed reconfigured: it's slow in CTk)
            for k in KEYS:
                has = o[k] is not None                          # (the block has it: x takes it out; else greyed, + adds it)
                if looks.get(k) != has:                         # (greyed: the block hasn't the line, the game's default)
                    self.key_labels[k].configure(text_color=TEXT if has else MUTED); looks[k] = has
                if k in self.flags:
                    v = has and bool(num(o[k]))
                    if self.flags[k].get() != v: self.flags[k].set(v)
                else:
                    v = o[k] if has else DEFAULT.get(k, '0')
                    if self.values[k].get() != v: self.values[k].set(v)
            self.row_looks = looks
            names = self.bitmap_names() if on(o['bitmap']) else self.faces
            if names != getattr(self, 'name_values', None): self.value_widgets['name'].configure(values=names); self.name_values = names
        finally:
            self.loading = False
        self.name_label.configure(text=font)
        self.scheme_label.configure(text=SCHEMES[short][:-4])
        self.describe()
        if self.raw.get(): self.show_raw()

    def toggle_raw(self):
        """Raw on: the right side is the font's block, as the file has it; off: its options again."""
        raw = self.raw.get()
        if self.side_view.get() != ('Raw' if raw else 'Options'): self.side_view.set('Raw' if raw else 'Options')
        self.root.update_idletasks()                            # (the toggle drawn in its new state before the work)
        self.set_active(self.active)
        with frozen(self.raw_box.master):                       # (the swap shown in one go, not half drawn)
            if raw:                                             # (laid over the options, which stay as they are: hiding
                self.raw_box.grid(row=1, column=0, rowspan=3, sticky='nsew', padx=GAP, pady=(10, 0))   # them made their
                self.raw_box.lift()                             # ~250 windows reappear in two goes, the Raw text showing)
            else: self.raw_box.grid_remove()

    def show_raw(self):
        """The block from the HUD's copy (as changed here, not saved yet), else the #base file that has it."""
        short, font = self.active.split(': ', 1)
        found = next(((p, got) for p in self.scheme_files.get(short, []) if (got := C.block_text(self.read(p), font))), None)
        self.raw_box.configure(state='normal'); self.raw_box.delete('1.0', 'end')
        if found:
            p, (line, text) = found
            rows = text.split('\n')
            lead = min((len(r) - len(r.lstrip('\t ')) for r in rows if r.strip()), default=0)
            self.raw_box.insert('1.0', '\n'.join(r[lead:] if r.strip() else '' for r in rows))   # (from the left edge)
            self.scheme_label.configure(text=f'{os.path.basename(p)}   ·   line {line}')
        self.raw_box.configure(state='disabled')

    def describe(self):
        """Under the name: the yres the entry gets, and the size it's drawn."""
        if not self.active: return
        key, yres, before, d = self.target(self.active)
        f = self.font(self.active)[0]
        where = f'yres {yres.replace(" ", "–")}' if yres else 'grows with the screen'
        size = f'{f.height} px' if f else self.errors.get(self.active, '')
        self.yres_label.configure(text=f'{where}   ·   {size}')

    def present(self, o):
        """The options the block has, in its order (added ones last; Bitmap always last, so ticking it never moves it)."""
        have = [k for k in o['_order'] if k in KEYS and o[k] is not None] + [k for k in KEYS if o[k] is not None and k not in o['_order']]
        return [k for k in have if k != 'bitmap'] + (['bitmap'] if 'bitmap' in have else [])

    def set_key(self, o, k, v):
        """An option in (v) or out (None) of the block, its place kept, or last if new."""
        o[k] = v
        if v is None and k in o['_order']: o['_order'].remove(k)
        elif v is not None and k not in o['_order']: o['_order'].append(k)

    def sort_rows(self, o):
        """The rows: the options the block has, in its order (draggable), a line, then the ones it hasn't."""
        have, rest = self.present(o), [k for k in KEYS if o[k] is None]
        if (have, rest) == getattr(self, 'row_order', None): return   # (as they are: nothing re-laid out)
        self.row_order = (have, rest)
        for i, k in enumerate(have + [None] + rest):
            if k is None:
                if have and rest: self.divider.grid(row=i, column=0, sticky='ew', padx=12, pady=10)
                else: self.divider.grid_remove()
                continue
            self.rows[k].grid(row=i, column=0, sticky='ew')
            self.key_labels[k].configure(cursor='fleur' if o[k] is not None else '')

    def drag_start(self, k, e):
        """A row of the block's picked up (nothing moves until the pointer does: a click stays a click)."""
        if not self.active or self.state(self.active)[k] is None: return
        self.dragging = {'key': k, 'press': e.y_root, 'moving': False}

    def drag_move(self, e):
        d = self.dragging
        if not d: return
        d['pointer'] = e.y_root
        if d['moving'] or abs(e.y_root - d['press']) < 4: return
        # the block's rows taken out of the grid and placed where they are, a gap of their height kept in the grid
        have = self.present(self.state(self.active))
        sc = self.rows[have[0]]._get_widget_scaling()
        d.update(moving=True, have=have, sc=sc, top=self.rows[have[0]].winfo_y(),
                 h={x: self.rows[x].winfo_height() for x in have}, y={x: float(self.rows[x].winfo_y()) for x in have},
                 grab=e.y_root - self.rows[d['key']].winfo_rooty())
        total = sum(d['h'].values())
        for x in have: self.rows[x].grid_remove()
        self.drag_room.configure(height=total / sc); self.drag_room.grid(row=0, column=0, rowspan=len(have), sticky='ew')
        self.drag_room.lower()                                  # (under the rows it holds the place of)
        for x in have: self.rows[x].place(x=0, y=d['y'][x] / sc, relwidth=1.0)
        self.rows[d['key']].configure(fg_color=HOVER); self.rows[d['key']].lift()
        self.drag_frame()

    def drag_spot(self):
        """Where the dragged row would go among the others, from where it is now."""
        d = self.dragging
        y = d['pointer'] - self.options_list.winfo_rooty() - d['grab'] - d['top']
        each = sum(d['h'].values()) / len(d['have'])
        return max(0, min(len(d['have']) - 1, int((y + each / 2) // each)))

    def drag_frame(self):
        """One frame: the dragged row under the pointer, the others easing toward their places around its gap."""
        d = self.dragging
        if not d or not d.get('moving'): return
        k, i = d['key'], self.drag_spot()
        order = [x for x in d['have'] if x != k]; order.insert(i, k)
        y, spots = d['top'], {}
        for x in order: spots[x] = y; y += d['h'][x]
        low, high = d['top'], d['top'] + sum(d['h'].values()) - d['h'][k]
        d['y'][k] = max(low, min(high, d['pointer'] - self.options_list.winfo_rooty() - d['grab']))
        for x in order:
            if x != k: d['y'][x] += (spots[x] - d['y'][x]) * 0.35
            self.rows[x].place_configure(y=round(d['y'][x]))   # (plain tkinter: pixels, not scaled like CTk's place)
        self.rows[k].lift()
        d['timer'] = self.root.after(15, self.drag_frame)

    def drag_end(self, e):
        """The row dropped: the block's lines in the new order, the rows back in the grid."""
        d, self.dragging = self.dragging, None
        if not d or not d.get('moving'): return
        if d.get('timer'): self.root.after_cancel(d['timer'])
        d['pointer'] = e.y_root; self.dragging = d
        i = self.drag_spot(); self.dragging = None
        for x in d['have']: self.rows[x].place_forget()
        self.drag_room.grid_remove()
        self.rows[d['key']].configure(fg_color='transparent')
        self.row_order = None                                   # (the rows were taken out of the grid: put back in any case)
        self.move_key(d['key'], i)

    def move_key(self, k, i):
        """An option the block has moved to place i among them (the order its lines are written in)."""
        o = self.state(self.active)
        have = [x for x in self.present(o) if x != k]
        have.insert(max(0, min(i, len(have))), k)
        o['_order'] = have + [x for x in o['_order'] if x not in have]
        self.sort_rows(o); self.edited()

    def flagged(self, k):
        """A tick: the flag's line in the block ("1"); unticked: out of it (the game's default, off)."""
        if self.loading or not self.active: return
        if k == 'bitmap': return self.switch_bitmap(self.flags[k].get())
        self.set_key(self.state(self.active), k, '1' if self.flags[k].get() else None)
        self.set_active(self.active, resort=False); self.edited()

    def valued(self, k):
        """A value: its line in the block; the game's default (blur 0, scale 1...): out of it."""
        if self.loading or not self.active: return
        v = self.values[k].get().strip()
        if not v or v.startswith('─'): return
        o, out = self.state(self.active), False
        if KIND[k] in ('int', 'num'):                           # (half typed, or not a number: not taken)
            try: out = float(v) == float(DEFAULT.get(k, '0'))
            except ValueError: return
        if (None if out else v) == o[k]: return
        had = o[k] is not None
        self.set_key(o, k, None if out else v)
        if had != (o[k] is not None): self.set_active(self.active, resort=False)
        self.edited()

    def edited(self):
        if self.tree.exists(self.active): self.tree.item(self.active, text=self.label(self.active))
        self.describe(); self.later()
        if self.timers.get('apply'): self.root.after_cancel(self.timers['apply'])
        self.pending = self.active                              # (into the scheme a moment after the last change)
        self.timers['apply'] = self.root.after(350, self.flush)

    def flush(self):
        """The change waiting to go into the scheme, now (before Save, Undo, another font...)."""
        if self.timers.get('apply'): self.root.after_cancel(self.timers['apply'])
        self.timers['apply'] = None
        iid, self.pending = getattr(self, 'pending', None), None
        if iid: self.apply(iid)

    def bitmap_names(self):
        """The bitmap fonts there are: made here (newest first), then the HUD's whose files are there."""
        names = self.made_names + [n for items in self.schemes.values() for n, v in (C.find(items, 'BitmapFontFiles') or []) if isinstance(v, str)]
        found = lambda n: n.lower() in self.made or all(os.path.isfile(p) for p in self.bitmaps.get(n.lower(), ('',)))
        seen = {}
        for n in names:
            if found(n): seen.setdefault(n.lower(), n)
        return list(seen.values())

    def switch_bitmap(self, on, name=None):
        """Bitmap on: the font is a bitmap one (name, else the one it names if it's one, else the newest). Off: the face
        it had before."""
        key = (self.active, self.h())
        o = self.state(self.active)
        names = self.bitmap_names()
        lower = {n.lower() for n in names}
        if on:
            if not name and not names:
                self.set_active(self.active, resort=False); self.flash('No bitmap fonts in this HUD yet: Create bitmap font makes one'); return
            if (o['name'] or '').lower() not in lower: self.face_before[key] = o['name']
            self.set_key(o, 'bitmap', '1')
            self.set_key(o, 'name', name or (o['name'] if (o['name'] or '').lower() in lower else names[0]))
        else:
            self.set_key(o, 'bitmap', None)
            if (o['name'] or '').lower() in lower: self.set_key(o, 'name', self.face_before.get(key) or self.plain_face(key))
        self.set_active(self.active, resort=False); self.edited()

    def plain_face(self, key):
        """The face a font had when the app opened, if it wasn't a bitmap one."""
        start = self.start_opts.get(key) or {}
        return start.get('name') if not on(start.get('bitmap')) and start.get('name') else 'Tahoma'

    def apply(self, iid=None):
        """The right side's block written as this screen's entry, into the app's copy (a change made: by itself)."""
        iid = iid or self.active
        if not iid: return
        short, font = iid.split(': ', 1)
        key, yres, before, d = self.target(iid)
        o, cur = self.state(iid), self.current(iid)
        mine = [p for p in self.scheme_files.get(short, []) if p in self.texts]
        where = next((p for p in mine if C.has_block(self.texts[p], font)), None) or next((p for p in mine if C.has_fonts(self.texts[p])), None)
        if not where: self.flash(f'This HUD has no {SCHEMES[short]} of its own with fonts in it'); return
        if self.scales(iid):                                   # (in place: a #base file's key would come back)
            based = self.base_keys(short, font, key, where)
            for k in KEYS:
                if o[k] is None and k in based and (KIND[k] is None or k in ('blur', 'scanlines')): d[k] = '0'
        text = self.texts[where]
        if on(o['bitmap']) and d.get('name', '').lower() not in self.bitmaps:
            text = C.add_bitmap_file(text, d['name'], f'materials/vgui/fonts/{d["name"]}.vbf')
        try: text = C.set_font_entry(text, font, key, d, before=before)
        except ValueError as ex: self.flash(str(ex)); return
        mine_now = copy.deepcopy(o)
        for k in [k for k in self.opts if k[0] == iid]: self.opts.pop(k); self.start_opts.pop(k, None)
        self.opts[(iid, self.h())], self.start_opts[(iid, self.h())] = mine_now, copy.deepcopy(mine_now)   # (the HUD's now)
        new = key not in [k for k, _ in self.entries(iid)]
        if self.change(f'{font} entry {key}', {where: text}) and new:   # (a new entry: said where; else the Save dot says it)
            self.flash(f'{font}: a new entry "{key}" ({yres.replace(" ", "–") if yres else "grows with the screen"}) in '
                       f'{os.path.basename(where)}, not saved yet')
        if iid == self.active: self.set_active(iid, resort=False)
        self.fill_tree()

    def base_keys(self, short, font, key, where):
        """The keys the scheme's other files (its #base ones) give this font's entry `key`."""
        out = set()
        for p in self.scheme_files.get(short, []):
            if p == where: continue
            root = next((v for k, v in C.parse_kv(self.read(p)) if isinstance(v, list)), [])
            out |= set(dict(C.font_entries(root, font)).get(key, {}))
        return out

    def add_font_to_hud(self):
        """Add font to HUD: the face's file into the HUD's resource/fonts, listed in CustomFontFiles (the game loads
        only those and the PC's own fonts)."""
        if not self.active: return
        self.flush()                                            # (an edit waiting goes in first: Undo takes back in order)
        o = self.state(self.active)
        if on(o['bitmap']): self.flash('A bitmap font is in the HUD once made'); return
        face, weight, italic = o['name'] or '', num(o['weight'], 400) or 400, on(o['italic'])
        try: data, ext = C.font_file(face, weight, italic)
        except ValueError as ex: self.flash(str(ex)); return
        stem = (re.sub(r'[^\w\-]+', '', face.replace(' ', ''), flags=re.ASCII) or 'font') + f'-{weight}' + ('-Italic' if italic else '')
        folder = os.path.join(self.hud, 'resource', 'fonts')
        dest, created = os.path.join(folder, stem + ext), []
        if os.path.isfile(dest) and open(dest, 'rb').read() != data: dest = os.path.join(folder, f'{stem}-{len(data)}{ext}')
        main = os.path.join(self.hud, 'resource', 'ClientScheme.res')
        if main not in self.texts: self.flash('This HUD has no ClientScheme.res'); return
        rel = 'resource/fonts/' + os.path.basename(dest)
        n = max([num(k) for k, _ in (C.find(self.schemes.get('Client', []), 'CustomFontFiles') or [])] + [0]) + 1
        try: text = C.add_custom_font(self.texts[main], rel, str(n))
        except ValueError as ex: self.flash(str(ex)); return
        if not os.path.isfile(dest):
            os.makedirs(folder, exist_ok=True)
            write_atomic(dest, data)
            created.append(dest)
        if self.change(f'add {face} {weight} to the HUD', {main: text}, created):
            self.flash(f'{face} {weight}: {rel}, listed in CustomFontFiles, not saved yet')
        else: self.flash(f'{face} {weight} is in the HUD already')

    # ---- drawing -----------------------------------------------------------------------------------------------------
    def font(self, iid):
        """The font for a font block as the right side has it, drawn at this screen: (font or None, entry)."""
        key, yres, before, d = self.target(iid)
        e = C.sized(d, self.h(), yres is None)
        ck = (iid, *e[1:], tuple(sorted(e[0].items())))
        if ck in self.cache: self.cache[ck] = self.cache.pop(ck)          # (last used: last)
        else:
            try: self.cache[ck] = C.make_font(e, {**self.made, **self.bitmaps}); self.errors.pop(iid, None)
            except Exception as ex: self.errors[iid] = str(ex); return None, e
            while len(self.cache) > 64: self.cache.pop(next(iter(self.cache))).close()   # (each holds drawing handles)
        return self.cache[ck], e

    def copies(self, iid):
        """How many times the game draws it: once, or for the servers' HudMsg font, once per send still held."""
        if self.draw_kind.get() != 'Real to game' or iid != HUDMSG: return 1
        now, hold = time.monotonic(), HOLD[self.mode.get()]
        return max(1, min(16, sum(1 for t in self.sends if now - t < hold)))

    def lines(self):
        """[(iid, font, [lines], colour)] for the mode."""
        mode = self.mode.get()
        if mode == 'Custom':
            sel = [i for i in self.tree.selection() if ': ' in i] or ([self.active] if self.active else [])
            return [(i, self.font(i)[0], [self.text.get() or ' '], self.colour) for i in sel]
        if not self.active: return []
        f = self.font(self.active)[0]
        if mode == 'Speedometer': return [(self.active, f, [f'{self.speed:>4}'], self.speed_colour)]
        return [(self.active, f, self.jtext.split('\n'), self.jcolour)]

    def render(self):
        """The screen with the text in its middle, as the game draws it."""
        if self.timers.get('render'): self.root.after_cancel(self.timers['render'])
        self.timers['render'] = None
        size = self.screen_size()
        if not size: return
        sw, sh = size
        scene = self.background_array(sw, sh).copy()
        everything = self.lines()
        items = [(i, f, ls, c) for i, f, ls, c in everything if f]
        gap = lambda f: f.height // 3
        total = sum(len(ls) * f.height + gap(f) for _, f, ls, _ in items) - (gap(items[-1][1]) if items else 0)
        y, box = (sh - total) // 2, [sw, sh, 0, 0]
        for iid, f, ls, colour in items:
            n = self.copies(iid)
            for line in ls:                                     # each line centred, a font's height apart (HudMsg)
                w = C.layout(f, line)[1]
                x = (sw - w) // 2
                C.draw_np(scene, f, line, x, y, (*colour, 255), n)
                box = [min(box[0], x), min(box[1], y), max(box[2], x + w), max(box[3], y + f.height)]
                y += f.height
            y += gap(f)
        self.scene = scene
        if self.recentre and box[2] > box[0]:
            self.centre, self.recentre = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2], False
        self.show()
        failed = [i for i, f, _, _ in everything if not f]
        if failed: self.flash(f'{failed[0].split(": ", 1)[1]} not drawn: {self.errors.get(failed[0], "")}')
        self.expiry()

    def expiry(self):
        """Real to game: drawn again when a held send runs out."""
        if self.timers.get('expire'): self.root.after_cancel(self.timers['expire']); self.timers['expire'] = None
        if self.draw_kind.get() != 'Real to game': return
        now, hold = time.monotonic(), HOLD[self.mode.get()]
        ends = [t + hold for t in self.sends if t + hold > now]
        if ends: self.timers['expire'] = self.root.after(int((min(ends) - now) * 1000) + 1, self.render)

    def show(self):
        """The part of the screen in view, zoomed (hard pixels in, smoothed out)."""
        if self.scene is None: return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        if cw < 2 or ch < 2: return
        sh, sw = self.scene.shape[:2]
        z = self.zoom
        left, top = self.centre[0] - cw / (2 * z), self.centre[1] - ch / (2 * z)
        x0, y0 = max(0, int(left)), max(0, int(top))
        x1, y1 = min(sw, int(left + cw / z) + 1), min(sh, int(top + ch / z) + 1)
        self.zoom_label.configure(text=f'{z * 100:g}%')
        if x1 <= x0 or y1 <= y0: self.canvas.itemconfigure(self.picture, image=''); return
        img = Image.fromarray(self.scene[y0:y1, x0:x1])
        if z != 1: img = img.resize((max(1, round((x1 - x0) * z)), max(1, round((y1 - y0) * z))), Image.NEAREST if z > 1 else Image.BOX)
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.itemconfigure(self.picture, image=self.photo)
        self.canvas.coords(self.picture, round((x0 - left) * z), round((y0 - top) * z))

    def wheel(self, e):
        """Zoom, the screen's pixel under the pointer kept under it."""
        i = min(range(len(ZOOMS)), key=lambda k: abs(ZOOMS[k] - self.zoom))
        z2 = ZOOMS[max(0, min(len(ZOOMS) - 1, i + (1 if e.delta > 0 else -1)))]
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        px, py = self.centre[0] + (e.x - cw / 2) / self.zoom, self.centre[1] + (e.y - ch / 2) / self.zoom
        self.zoom, self.centre = z2, [px - (e.x - cw / 2) / z2, py - (e.y - ch / 2) / z2]
        self.show()

    def grab_view(self, e):
        self.drag = (e.x, e.y, *self.centre)

    def move_view(self, e):
        if not self.drag: return
        x, y, cx, cy = self.drag
        self.centre = [cx - (e.x - x) / self.zoom, cy - (e.y - y) / self.zoom]
        self.show()

    def reset_view(self):
        self.zoom, self.recentre = 1.0, True
        self.render()

    def background_array(self, w, h):
        """The whole screen behind the text, made once per choice and size: a colour, a texture, or a picture."""
        name = self.back.get()
        key = (name, id(self.bgimg) if name == 'Picture' else 0, w, h)
        if key not in self.back_cache:
            full = None
            if name == 'Picture' and self.bgimg is not None: full = self.bgimg.resize((w, h), Image.BILINEAR)
            elif name in TEXTURES:
                try:
                    if not getattr(self, 'pak', None): self.pak = C.VPK(PAK)
                    src = C.read_vtf(name, self.pak.read(f'materials/{TEXTURES[name]}.vtf'))[0].convert('RGB')
                    if TEXTURES[name].startswith('skybox/'): full = src.resize((w, h), Image.BILINEAR)
                    else:
                        z = max(1, round(h / 720))
                        tile = src.resize((src.width * z, src.height * z), Image.BILINEAR)
                        full = Image.new('RGB', (w, h))
                        for y in range(0, h, tile.height):
                            for x in range(0, w, tile.width): full.paste(tile, (x, y))
                except (OSError, KeyError, ValueError): full = None
            arr = np.array(full) if full is not None else np.full((h, w, 3), BACKS.get(name, BACKS['Dark grey']), np.uint8)
            self.back_cache = {key: arr}                       # (one at a time: a 4K screen is 25 MB)
        return self.back_cache[key]

    # ---- the modes -------------------------------------------------------------------------------------------------
    def restart(self, recentre=False):
        """Mode, font or timing changed: the moving texts run again, from now."""
        for k in ('send', 'expire', 'restart'):
            if self.timers.get(k): self.root.after_cancel(self.timers[k]); self.timers[k] = None
        self.sends = []
        custom = self.mode.get() == 'Custom'
        if custom: self.every_box.grid_remove(); self.text_entry.grid(row=0, column=0, sticky='ew'); self.colour_button.grid()
        else: self.text_entry.grid_remove(); self.every_box.grid(row=0, column=0, sticky='w'); self.colour_button.grid_remove()
        if recentre: self.recentre = True
        if not custom or self.draw_kind.get() == 'Real to game': self.send()
        else: self.later()

    def send(self):
        """The next text, as the servers send them: jhud each jump, the speedometer every few ticks, shavit's records
        every second."""
        mode = self.mode.get()
        if mode == 'Speedometer':
            prev = self.speed
            self.speed = max(1000, min(2500, prev + random.randint(-35, 45)))
            self.speed_colour = GAIN[4] if self.speed > prev else GAIN[3] if self.speed == prev else GAIN[0]
        elif mode == 'jhud':
            self.jump = self.jump % 16 + 1
            lo = JUMP_SPEEDS[self.jump - 1]
            speed = random.randint(lo[0] - 12, lo[3] + 8)
            speed_rank = sum(speed >= v for v in lo)           # (0 really bad .. 4 really good)
            if self.jump == 1: self.jtext, self.jcolour = f'1: {speed}', GAIN[speed_rank]
            else:
                gain, sync = random.uniform(55, 100), random.randint(60, 100)
                gain_rank = 4 if gain >= 90 else 3 if gain >= 80 else 2 if gain >= 70 else 1 if gain >= 60 else 0
                self.jtext = f'{self.jump}: {speed} ({sync}%)\n{gain:.2f}'
                self.jcolour = GAIN[speed_rank if self.jump <= 6 else gain_rank]
        now = time.monotonic()
        self.sends = [t for t in self.sends if now - t < 3.0] + [now]
        every = RESEND if mode == 'Custom' else max(1, min(1000, num(self.every.get(), 100))) / 1000
        self.timers['send'] = self.root.after(max(1, int(every * 1000)), self.send)
        self.later(ms=1)

    # ---- choices ---------------------------------------------------------------------------------------------------
    def pick_colour(self):
        c = colorchooser.askcolor(color='#%02x%02x%02x' % self.colour, parent=self.root)
        if c and c[0]:
            self.colour = tuple(map(int, c[0]))
            hx = '#%02x%02x%02x' % self.colour
            self.colour_button.configure(fg_color=hx, hover_color=hx); self.later()

    def pick_back(self, name):
        if name == 'Picture…':
            p = filedialog.askopenfilename(title='A game screenshot', filetypes=[('Pictures', '*.png *.jpg *.jpeg *.bmp')])
            self.bgimg = Image.open(p).convert('RGB') if p else None
            self.back.set('Picture' if p else 'Dark grey')
        self.later()

    def open_maker(self):
        m = getattr(self, 'maker', None)
        if m and m.win.winfo_exists(): m.win.deiconify(); m.win.lift(); return
        if self.active: self.maker = Maker(self)

class Maker:
    """Create bitmap font: a font made with every setting a picture of letters can hold, the game's effects grown past
    1 px, colours and opacity, a smooth outline and a box, saved into the HUD as a bitmap font."""
    def __init__(self, app, show=True):
        self.app, ui = app, app.ui
        self.opened_for = (app.hud, app.active)
        o = app.state(app.active)
        f = app.font(app.active)[0]
        tmp = not isinstance(f, C.Win32Font)
        if tmp:                                                 # (a bitmap one: from the face it had)
            face = app.face_before.get((app.active, app.h())) or app.plain_face((app.active, app.h()))
            f = C.Win32Font(face, max(8, num(o['tall'], 24)), num(o['weight'], 400), flags=C.FONTFLAG['antialias'])
        self.win = win = ctk.CTkToplevel(app.root, fg_color=BG)
        if not show: win.withdraw()
        win.title('Bitmap font'); win.geometry('1040x680'); win.minsize(940, 600); win.transient(app.root)
        win.columnconfigure(1, weight=1); win.rowconfigure(0, weight=1)
        self.v, self.colours, self.swatches = {}, {'letter': [255, 255, 255], 'edge': [0, 0, 0], 'box': [0, 0, 0]}, {}
        side = ui.panel(win); side.grid(row=0, column=0, sticky='nsew', padx=(GAP, 0), pady=GAP)
        lst = ctk.CTkScrollableFrame(side, fg_color=RAISED, corner_radius=R, width=330, scrollbar_button_color=FIELD,
                                     scrollbar_button_hover_color=HOVER)
        lst.pack(fill='both', expand=True, padx=GAP, pady=GAP); lst.columnconfigure(0, weight=1)
        def var(name, init, boolean=False):
            self.v[name] = (tk.BooleanVar if boolean else tk.StringVar)(value=bool(init) if boolean else str(init))
            self.v[name].trace_add('write', lambda *_: self.later())
            return self.v[name]
        def value(name, init, step=1, hi=None): return lambda box: ui.stepper(box, var(name, init), step, 0, hi).pack(side='right')
        def flag(name, init): return lambda box: ui.check(box, var(name, init, True)).pack(side='right')
        def face(name, init): return lambda box: ui.combo(box, app.faces, var(name, init), width=170).pack(side='right')
        def colour(name):
            def make(box):
                ui.label(box, '%', muted=True, width=18).pack(side='right', padx=(8, 0))
                ui.entry(box, var(name + '_a', 100), width=104).pack(side='right')
                self.swatches[name] = ui.swatch(box, self.colours[name], lambda: self.pick(name))
                self.swatches[name].pack(side='right', padx=(0, 8))
            return make
        F = C.FONTFLAG
        rows = [('Font', face('face', f.face)), ('Size (px)', value('size', f.tall, 1, 255)), ('Weight', value('weight', f.weight or 400, 100, 1000)),
                ('Anti-aliasing', flag('aa', f.aa)), ('Italic', flag('italic', f.flags & F['italic'])),
                ('Underline', flag('underline', f.flags & F['underline'])), ('Strike-out', flag('strikeout', f.flags & F['strikeout'])),
                ('Drop shadow (px)', value('drop', f.drop)), ('Outline (px)', value('outline', f.outline)),
                ('Smooth outline (px)', value('smooth', 0, 0.5)), ('Letter spacing (px)', value('spacing', 0)), ('Even gaps', flag('even', False)), ('Digits one width', flag('digits', True)), ('Digit width trim (px)', value('trim', 0)), ('Centre brackets', flag('centre', False)), ('Edge sharpness (%)', value('sharp', 0, 25, 100)), ('Blur', value('blur', f.blur)), ('Scan lines', value('scanlines', f.scanlines)),
                ('Rotary line', flag('rotary', f.rotary)), ('Letters', colour('letter')), ('Outline and shadow', colour('edge')),
                ('Box', flag('boxed', False)), ('Box padding (px)', value('pad', 4)), ('Box colour', colour('box'))]
        for i, (label, make) in enumerate(rows):
            ui.label(lst, label).grid(row=i, column=0, sticky='w', padx=(12, 8), pady=3)
            box = ctk.CTkFrame(lst, fg_color='transparent', height=H); box.grid(row=i, column=1, sticky='e', padx=(0, 10), pady=3)
            make(box)
        main = ui.panel(win); main.grid(row=0, column=1, sticky='nsew', padx=GAP, pady=GAP)
        main.columnconfigure(0, weight=1); main.rowconfigure(0, weight=1)
        view = ui.panel(main, BG); view.grid(row=0, column=0, sticky='nsew', padx=GAP, pady=(GAP, 0))
        self.canvas = tk.Canvas(view, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill='both', expand=True, padx=R // 2, pady=R // 2)
        self.canvas.bind('<Configure>', lambda e: self.later())
        foot = ctk.CTkFrame(main, fg_color='transparent'); foot.grid(row=1, column=0, sticky='ew', padx=GAP, pady=GAP)
        foot.columnconfigure(0, weight=1)
        self.name = tk.StringVar()
        ui.entry(foot, self.name, placeholder='Name').grid(row=0, column=0, sticky='ew')
        ui.button(foot, 'Cancel', self.close, width=110).grid(row=0, column=1, padx=(8, 0))
        ui.button(foot, 'Make', self.make, accent=True, width=110).grid(row=0, column=2, padx=(8, 0))
        self.msg = ui.label(main, '', muted=True); self.msg.grid(row=2, column=0, sticky='ew', padx=GAP + 2, pady=(0, GAP))
        self.timer, self.auto_name, self.font = None, '', None
        win.protocol('WM_DELETE_WINDOW', self.close)
        self.later(ms=10)
        if tmp: f.close()                                       # (only its settings were wanted)
        if show: dark_window(win)

    def pick(self, name):
        c = colorchooser.askcolor(color='#%02x%02x%02x' % tuple(self.colours[name]), parent=self.win)
        if c and c[0]:
            self.colours[name] = list(map(int, c[0]))
            hx = '#%02x%02x%02x' % tuple(self.colours[name])
            self.swatches[name].configure(fg_color=hx, hover_color=hx); self.later()

    def later(self, ms=150):
        if self.timer: self.win.after_cancel(self.timer)
        self.timer = self.win.after(ms, self.look)

    def n(self, name, lo=0, hi=200, d=0):
        return max(lo, min(hi, num(self.v[name].get(), d)))

    def settings(self):
        """(font, smooth outline px, box padding or None, style) from the settings."""
        F = C.FONTFLAG
        flags = sum(F[k] for k, v in (('antialias', 'aa'), ('italic', 'italic'), ('underline', 'underline'),
                                      ('strikeout', 'strikeout'), ('rotary', 'rotary')) if self.v[v].get())
        font = C.Win32Font(self.v['face'].get().strip() or 'Tahoma', self.n('size', 4, 255, 24), self.n('weight', 0, 1000, 400),
                           self.n('blur', 0, 40), self.n('scanlines', 0, 40), flags, drop=self.n('drop', 0, 40), outline=self.n('outline', 0, 40))
        if self.font: self.font.close()                         # (the last one: each holds Windows drawing handles)
        self.font = font
        style = {k: (*self.colours[k], self.n(k + '_a', 0, 100, 100) / 100) for k in ('letter', 'edge', 'box')}
        try: smooth = max(0.0, min(40.0, float(self.v['smooth'].get() or 0)))      # (halves too: 1.5)
        except ValueError: smooth = 0.0
        return font, smooth, (self.n('pad', 0, 100) if self.v['boxed'].get() else None), style

    def default_name(self, font, smooth, box):
        bits = [font.face, str(font.weight), str(font.tall)] + [f'{k}{n:g}' for k, n in (('s', font.drop), ('o', font.outline), ('so', smooth),
                                                                                    ('sp', self.n('spacing', 0, 100))) if n] + (['even' if self.v['digits'].get() else 'even_free'] if self.v['even'].get() else []) + (['mid'] if self.v['centre'].get() else []) + ([f"sharp{self.n('sharp', 0, 100)}"] if self.n('sharp', 0, 100) else []) + ([f"trim{self.n('trim', 0, 20)}"] if self.n('trim', 0, 20) else [])
        return re.sub(r'\W+', '_', '_'.join(bits) + ('_box' if box is not None else '')).lower()

    def look(self):
        """The text in the font as the game draws it now, and as the bitmap font these settings make."""
        self.timer = None
        try: font, smooth, box, style = self.settings()
        except ValueError as ex: self.msg.configure(text=str(ex)); return
        auto = self.default_name(font, smooth, box)
        if self.name.get() in ('', self.auto_name): self.name.set(auto)     # (a typed name stays)
        self.auto_name = auto
        a = self.app
        text = a.text.get() or 'Speed: 1284'
        base = os.path.join(a.tmp_dir(), 'look')
        C.bake(font, base, smooth, text, box, style, self.n('spacing', 0, 100), self.v['even'].get(), self.v['digits'].get(), self.v['centre'].get(), self.n('sharp', 0, 100), self.n('trim', 0, 20))
        bf = C.BitmapFont(base + '.vbf', base + '.vtf')
        rows = [f for f in (a.font(a.active)[0] if a.active else None, bf) if f]   # (the font now, then the bitmap one)
        tw = max(C.layout(f, text)[1] for f in rows)
        th = sum(f.height for f in rows) + 40 * (len(rows) - 1)
        cw, ch = max(2, self.canvas.winfo_width()), max(2, self.canvas.winfo_height())
        z = max(1, min(4, int(min((cw - 40) / max(1, tw), (ch - 40) / max(1, th)))))     # (hard pixels, as big as fits)
        w, h = -(-cw // z), -(-ch // z)
        sw, sh = a.screen_size() or (2560, 1440)
        arr = np.zeros((h, w, 3), np.uint8); bg = a.background_array(sw, sh)[:h, :w]; arr[:bg.shape[0], :bg.shape[1]] = bg
        y = (h - th) // 2
        for f in rows:
            C.draw_np(arr, f, text, (w - C.layout(f, text)[1]) // 2, y, (*a.colour, 255)); y += f.height + 40
        img = Image.fromarray(arr)
        if z > 1: img = img.resize((w * z, h * z), Image.NEAREST)
        self.photo = ImageTk.PhotoImage(img)
        self.canvas.delete('all'); self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        self.msg.configure(text=f'{bf.height} px tall')

    def make(self):
        n = self.name.get().strip()
        if not re.fullmatch(r'[A-Za-z0-9_\-]+', n): self.msg.configure(text='Name: letters, digits, _ and - only'); return
        a = self.app
        a.flush()                                               # (an edit waiting goes in first: Undo takes back in order)
        if (a.hud, a.active) != self.opened_for:
            self.msg.configure(text='The HUD or font changed since this opened: close it and open it again'); return
        main = os.path.join(a.hud, 'resource', 'ClientScheme.res')
        if main not in a.texts: self.msg.configure(text='This HUD has no ClientScheme.res'); return
        try: font, smooth, box, style = self.settings()
        except ValueError as ex: self.msg.configure(text=str(ex)); return
        folder = os.path.join(a.hud, 'materials', 'vgui', 'fonts')
        os.makedirs(folder, exist_ok=True)
        base = os.path.join(folder, n)
        if n.lower() not in a.made and any(os.path.isfile(base + e) for e in ('.vbf', '.vtf')):
            self.msg.configure(text=f'The HUD has a font named {n} already: pick another name'); return
        try: text = C.add_bitmap_file(a.texts[main], n, f'materials/vgui/fonts/{n}.vbf')
        except ValueError as ex: self.msg.configure(text=str(ex)); return
        created = [p for p in (base + '.vbf', base + '.vtf') if not os.path.isfile(p)]
        C.bake(font, base, smooth, C.BAKE, box, style, self.n('spacing', 0, 100), self.v['even'].get(), self.v['digits'].get(), self.v['centre'].get(), self.n('sharp', 0, 100), self.n('trim', 0, 20))
        a.made[n.lower()] = (base + '.vbf', base + '.vtf'); a.made_names.insert(0, n)
        a.change(f'bitmap font {n}', {main: text}, created)
        a.switch_bitmap(True, n)
        a.flash(f'Made {n}: Save, then restart the game')
        self.close()

    def close(self):
        if self.timer: self.win.after_cancel(self.timer)
        if self.font: self.font.close(); self.font = None
        self.win.destroy()

if __name__ == '__main__':
    try:
        import ctypes; ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception: pass
    ctk.set_appearance_mode('dark')
    selftest = len(sys.argv) > 2 and sys.argv[1] == '--selftest'
    root = ctk.CTk(fg_color=BG)
    if selftest: root.withdraw()                             # (the exe's check: no window; "ok" or what failed, to a file)
    root.geometry('1520x900'); root.minsize(1220, 720)
    icon = os.path.join(BUNDLE, 'icon.ico')
    if os.path.isfile(icon): root.iconbitmap(icon)
    if selftest:                                            # (on a HUD of its own: works on any PC, touches nothing)
        try:
            hud = os.path.join(tempfile.mkdtemp(), 'selftest')
            os.makedirs(os.path.join(hud, 'resource'))
            with open(os.path.join(hud, 'resource', 'ClientScheme.res'), 'w') as f:
                f.write('"Scheme" { Fonts { CenterPrintText { "1" { "name" "Tahoma" "tall" "18" } } } }' + chr(10))
            SETTINGS = os.path.join(hud, 'settings.json')
            app = App(root); app.pick_hud(hud)
            app.tree.selection_set(['Client: CenterPrintText']); app.picked(); app.render()
            ok = app.scene is not None and C.faces()
            msg = 'ok' if ok else 'nothing drawn'
        except Exception as e:
            msg = f'{type(e).__name__}: {e}'
        open(sys.argv[2], 'w', encoding='utf-8').write(msg)
        root.destroy(); sys.exit(0)
    try: app = App(root)
    except Exception as e:                                  # (a HUD that can't be read: said so, not opened next time)
        messagebox.showerror('Font Tester', f'Could not open the HUD: {type(e).__name__}: {e}')
        save_settings({k: v for k, v in load_settings().items() if k not in ('hud', 'selection', 'active')})
        sys.exit(1)
    root.report_callback_exception = lambda kind, ex, tb: app.flash(f'Something went wrong: {kind.__name__}: {ex}')
    root.protocol('WM_DELETE_WINDOW', lambda: app.confirm_discard() and root.destroy())
    dark_window(root); root.mainloop()
