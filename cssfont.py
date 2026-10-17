# cssfont.py: Counter-Strike: Source's HUD text, drawn the way the game draws it, without the game.
#
# What the game does (vgui's Win32 font, its font effects, the scheme's font loading and the surface's text drawing;
# read from the game's code and DLLs, see README.md), redone here with the same Windows calls:
#   - each letter: CreateFontA(tall, weight, ANSI_CHARSET, ANTIALIASED_QUALITY or NONANTIALIASED_QUALITY), then
#     GetGlyphOutlineA(GGO_GRAY8_BITMAP) when anti-aliased (alpha = level * 255 / 64), else ExtTextOutW white on black
#     into a bitmap (alpha from brightness), in a cell 2 px wider than its ABC width b (+ effects) and 2 px taller than the font;
#     characters past 0xFF from Tahoma (every face but Marlett and Tahoma), at the font's height;
#   - effects in the game's order: drop shadow, outline, blur, scan lines, rotary line;
#   - the line: each letter at pen + a (underlined: at the pen), pen moves by a + b + c, spaces drawn too;
#   - blending in linear light (gamma 2.2), and server texts drawn as many times as they're held over;
#   - the scheme: #base files filled in under the file's own keys, [$WIN32]-style conditions, CustomFontFiles loaded,
#     a font's first entry whose yres fits the scheme's screen height, proportional entries without yres scaled by
#     height / 480, tall capped at 255, missing faces falling back (Verdana and Trebuchet MS to Arial, others to Tahoma);
#   - bitmap fonts ("bitmap" "1", BitmapFontFiles): letters cut from a .vbf's page picture, scaled (BitmapFont), and
#     made here from any Win32 font, effects and all (bake).
import ctypes, math, os, re, struct
import numpy as np
from ctypes import wintypes as W
from PIL import Image, ImageChops

gdi = ctypes.WinDLL('gdi32', use_last_error=True)

class TEXTMETRICA(ctypes.Structure):
    _fields_ = [(n, W.LONG) for n in ('tmHeight', 'tmAscent', 'tmDescent', 'tmInternalLeading', 'tmExternalLeading',
                                     'tmAveCharWidth', 'tmMaxCharWidth', 'tmWeight', 'tmOverhang', 'tmDigitizedAspectX',
                                     'tmDigitizedAspectY')] + [(n, ctypes.c_ubyte) for n in ('tmFirstChar', 'tmLastChar',
                                     'tmDefaultChar', 'tmBreakChar', 'tmItalic', 'tmUnderlined', 'tmStruckOut',
                                     'tmPitchAndFamily', 'tmCharSet')]
class GLYPHMETRICS(ctypes.Structure):
    _fields_ = [('gmBlackBoxX', W.UINT), ('gmBlackBoxY', W.UINT), ('gmptGlyphOrigin', W.POINT), ('gmCellIncX', ctypes.c_short), ('gmCellIncY', ctypes.c_short)]
class FIXED(ctypes.Structure): _fields_ = [('fract', W.WORD), ('value', ctypes.c_short)]
class MAT2(ctypes.Structure): _fields_ = [('eM11', FIXED), ('eM12', FIXED), ('eM21', FIXED), ('eM22', FIXED)]
class ABC(ctypes.Structure): _fields_ = [('abcA', ctypes.c_int), ('abcB', W.UINT), ('abcC', ctypes.c_int)]
class LOGFONTA(ctypes.Structure):
    _fields_ = [(n, W.LONG) for n in ('lfHeight', 'lfWidth', 'lfEscapement', 'lfOrientation', 'lfWeight')] + \
               [(n, ctypes.c_ubyte) for n in ('lfItalic', 'lfUnderline', 'lfStrikeOut', 'lfCharSet', 'lfOutPrecision',
                                             'lfClipPrecision', 'lfQuality', 'lfPitchAndFamily')] + [('lfFaceName', ctypes.c_char * 32)]
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', W.DWORD), ('biWidth', W.LONG), ('biHeight', W.LONG), ('biPlanes', W.WORD), ('biBitCount', W.WORD),
                ('biCompression', W.DWORD), ('biSizeImage', W.DWORD), ('biXPelsPerMeter', W.LONG), ('biYPelsPerMeter', W.LONG),
                ('biClrUsed', W.DWORD), ('biClrImportant', W.DWORD)]

ENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, W.DWORD, W.LPARAM)
for name, res, args in [
        ('CreateCompatibleDC', W.HDC, [W.HDC]), ('DeleteDC', W.BOOL, [W.HDC]), ('DeleteObject', W.BOOL, [W.HGDIOBJ]),
        ('CreateFontA', W.HFONT, [ctypes.c_int] * 5 + [W.DWORD] * 8 + [ctypes.c_char_p]),
        ('SelectObject', W.HGDIOBJ, [W.HDC, W.HGDIOBJ]), ('SetMapMode', ctypes.c_int, [W.HDC, ctypes.c_int]),
        ('SetTextAlign', W.UINT, [W.HDC, W.UINT]), ('GetTextMetricsA', W.BOOL, [W.HDC, ctypes.POINTER(TEXTMETRICA)]),
        ('GetCharABCWidthsW', W.BOOL, [W.HDC, W.UINT, W.UINT, ctypes.POINTER(ABC)]),
        ('GetGlyphOutlineA', W.DWORD, [W.HDC, W.UINT, W.UINT, ctypes.POINTER(GLYPHMETRICS), W.DWORD, ctypes.c_void_p, ctypes.POINTER(MAT2)]),
        ('CreateDIBSection', W.HBITMAP, [W.HDC, ctypes.c_void_p, W.UINT, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD]),
        ('SetBkColor', W.COLORREF, [W.HDC, W.COLORREF]), ('SetTextColor', W.COLORREF, [W.HDC, W.COLORREF]),
        ('SetBkMode', ctypes.c_int, [W.HDC, ctypes.c_int]), ('MoveToEx', W.BOOL, [W.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]),
        ('ExtTextOutW', W.BOOL, [W.HDC, ctypes.c_int, ctypes.c_int, W.UINT, ctypes.POINTER(W.RECT), W.LPCWSTR, W.UINT, ctypes.c_void_p]),
        ('GdiFlush', W.BOOL, []), ('EnumFontFamiliesExA', ctypes.c_int, [W.HDC, ctypes.POINTER(LOGFONTA), ENUMPROC, W.LPARAM, W.DWORD]),
        ('AddFontResourceExW', ctypes.c_int, [W.LPCWSTR, W.DWORD, ctypes.c_void_p]),
        ('RemoveFontResourceExW', W.BOOL, [W.LPCWSTR, W.DWORD, ctypes.c_void_p]),
        ('GetFontData', W.DWORD, [W.HDC, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD])]:
    f = getattr(gdi, name); f.restype = res; f.argtypes = args

FONTFLAG = {'italic': 0x1, 'underline': 0x2, 'strikeout': 0x4, 'symbol': 0x8, 'antialias': 0x10, 'blur': 0x20,
            'rotary': 0x40, 'dropshadow': 0x80, 'additive': 0x100, 'outline': 0x200, 'custom': 0x400, 'bitmap': 0x800}
FALLBACK = {'verdana': 'Arial', 'trebuchet ms': 'Arial', 'tahoma': None}

def face_exists(name):
    found = [False]
    def cb(*_): found[0] = True; return 0
    lf = LOGFONTA(); lf.lfCharSet = 1; lf.lfFaceName = name.encode('mbcs', 'replace')[:31]   # DEFAULT_CHARSET
    dc = gdi.CreateCompatibleDC(None)
    gdi.EnumFontFamiliesExA(dc, ctypes.byref(lf), ENUMPROC(cb), 0, 0)
    gdi.DeleteDC(dc)
    return found[0]

class Win32Font:
    """One glyph set: a face at a pixel height, with the game's effects. Cells are RGBA arrays, height x b.
    drop, outline: their sizes in px when not the game's 1 (from the flags), for bitmap fonts made here."""
    def __init__(self, face, tall, weight=0, blur=0, scanlines=0, flags=0, drop=None, outline=None):
        self.requested, self.args, self.foreign = face, (tall, weight, blur, scanlines, flags, drop, outline), None
        while face and not face_exists(face):                   # the game's fallback chain
            face = FALLBACK.get(face.lower(), 'Tahoma')
        if not face: raise ValueError(f'no font for {self.requested!r}')
        self.face, self.tall, self.weight, self.flags = face, tall, weight, flags
        self.aa = bool(flags & FONTFLAG['antialias'])
        self.drop = drop if drop is not None else 1 if flags & FONTFLAG['dropshadow'] else 0
        self.outline = outline if outline is not None else 1 if flags & FONTFLAG['outline'] else 0
        self.blur, self.scanlines = blur, scanlines
        self.rotary, self.additive = bool(flags & FONTFLAG['rotary']), bool(flags & FONTFLAG['additive'])
        self.underline = bool(flags & FONTFLAG['underline'])
        self.dc = gdi.CreateCompatibleDC(None)
        charset = 2 if flags & FONTFLAG['symbol'] else 0        # SYMBOL_CHARSET / ANSI_CHARSET
        self.hfont = gdi.CreateFontA(tall, 0, 0, 0, weight, flags & 1, flags & 2, flags & 4, charset, 0, 0,
                                     4 if self.aa else 3, 0, face.encode('mbcs', 'replace'))
        gdi.SetMapMode(self.dc, 1); gdi.SelectObject(self.dc, self.hfont); gdi.SetTextAlign(self.dc, 0 | 0 | 1)   # TA_UPDATECP
        tm = TEXTMETRICA(); gdi.GetTextMetricsA(self.dc, ctypes.byref(tm))
        self.height = tm.tmHeight + self.drop + 2 * self.outline
        self.ascent, self.max_wide = tm.tmAscent, tm.tmMaxCharWidth
        self.bmp = (tm.tmMaxCharWidth + 2 * self.outline, tm.tmHeight + self.drop + 2 * self.outline)
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), self.bmp[0], -self.bmp[1], 1, 32, 0)
        self.bits = ctypes.c_void_p()
        self.dib = gdi.CreateDIBSection(self.dc, ctypes.byref(bi), 0, ctypes.byref(self.bits), None, 0)
        if not self.dib or not self.bits:
            gdi.DeleteObject(self.hfont); gdi.DeleteDC(self.dc); raise ValueError(f'{face} {tall}: too big to draw')
        gdi.SelectObject(self.dc, self.dib)
        self._abc, self._cells, self._shift = {}, {}, {}

    def close(self):
        if not self.dc: return                                  # (closed already)
        gdi.DeleteObject(self.hfont); gdi.DeleteObject(self.dib); gdi.DeleteDC(self.dc); self.dc = None
        if self.foreign: self.foreign.close()

    def other(self, ch):
        """The font that draws a character past 0xFF: Tahoma at the same size and effects. The game gives every face but
        Marlett and Tahoma only 0-0xFF and Tahoma the rest (vguimatsurface SetFontGlyphSet, read 2026-10-12)."""
        if ord(ch) <= 0xFF or self.requested.lower() in ('marlett', 'tahoma'): return None
        if not self.foreign: self.foreign = Win32Font('Tahoma', *self.args)
        return self.foreign

    def offset(self, ch):
        """How far a letter's cell is drawn from where the layout puts it (an underlined, smoothed letter: -a)."""
        if f := self.other(ch): return f.offset(ch)
        self.cell(ch)
        return self._shift.get(ch, 0)

    def abc(self, ch):
        """(a, b, c) as the game keeps them: widened for blur and outline, and the drop shadow's pixel."""
        if f := self.other(ch): return f.abc(ch)
        if ch not in self._abc:
            r = ABC()
            if gdi.GetCharABCWidthsW(self.dc, ord(ch), ord(ch), ctypes.byref(r)): a, b, c = r.abcA, r.abcB, r.abcC
            else: a, b, c = 0, self.max_wide, 0
            e = self.blur + self.outline
            self._abc[ch] = (a - e, b + 2 * e + self.drop, c - e - self.drop)
        return self._abc[ch]

    def cell(self, ch):
        if ch in self._cells: return self._cells[ch]
        if f := self.other(ch):                                 # (drawn at this font's height: Tahoma's cell squeezed
            c = f.cell(ch)                                      # or stretched to it, point-sampled; s4 Impact, 2026-10-12)
            t = self.height + 2
            rows = np.floor((np.arange(t) + 0.5) * c.shape[0] / t - 1e-4).astype(int)
            self._cells[ch] = c[np.clip(rows, 0, c.shape[0] - 1)]
            return self._cells[ch]
        a, b, c = self.abc(ch)
        # the game's cell is 2 px wider than b (an underlined letter's: than a + b + c) and 2 px taller than the font, its
        # effects (blur, the rotary line) reaching into them; spacing still by a, b, c (measured: CS:S x64 shots of
        # Arial 40/42 px, 2026-10-12)
        ul = self.underline
        wide, tall = max(0, (a + b + c) if ul else b) + 2, self.height + 2
        rgba = np.zeros((tall, wide, 4), np.uint8)
        n = 0
        gm, mat = GLYPHMETRICS(), MAT2(FIXED(0, 1), FIXED(0, 0), FIXED(0, 0), FIXED(0, 1))
        code = ord(ch)                                          # (the game hands the character's own code to the A call)
        if self.aa and (ord(ch) <= 0xFF or self.flags & FONTFLAG['custom']):   # (anti-aliased: Latin-1, or any with "custom")
            n = gdi.GetGlyphOutlineA(self.dc, code, 6, ctypes.byref(gm), 0, None, ctypes.byref(mat))
            if n == 0xFFFFFFFF: n = 0
        if n:
            buf = (ctypes.c_ubyte * n)()
            gdi.GetGlyphOutlineA(self.dc, code, 6, ctypes.byref(gm), n, buf, ctypes.byref(mat))
            bw, bh, pitch = gm.gmBlackBoxX, gm.gmBlackBoxY, (gm.gmBlackBoxX + 3) & ~3
            g = np.frombuffer(bytes(buf), np.uint8)[:bh * pitch].reshape(bh, pitch)[:, :bw]
            push = self.ascent - gm.gmptGlyphOrigin.y
            xstart = (bw - b) // 2 if bw >= b + 2 else 0
            g = g[:, xstart:]                                   # glyph column i lands at x = i + blur + outline
            x0 = self.blur + self.outline
            if ul: self._shift[ch] = -a                         # (underlined and smoothed: the cell goes a to the left)
            y_lo, y_hi = max(0, -push), min(bh, tall - push)   # (rows that land inside the cell)
            cols = max(0, min(g.shape[1], wide - x0))
            if y_hi > y_lo and cols > 0:
                part = g[y_lo:y_hi, :cols].astype(np.float64)
                alpha = (np.minimum(1.0, part / 64.0) * 255.0).astype(np.uint8)
                dst = rgba[y_lo + push:y_hi + push, x0:x0 + cols]
                lit = part > 0
                dst[lit] = 255; dst[..., 3][lit] = alpha[lit]
        else:                                                   # drawn by ExtTextOut, white on black
            gdi.SetBkColor(self.dc, 0); gdi.SetTextColor(self.dc, 0xFFFFFF); gdi.SetBkMode(self.dc, 2)
            gdi.MoveToEx(self.dc, -a, 0, None)
            rect = W.RECT(0, 0, wide, tall)
            gdi.ExtTextOutW(self.dc, 0, 0, 2, ctypes.byref(rect), None, 0, None)      # ETO_OPAQUE: clear
            gdi.ExtTextOutW(self.dc, 0, 0, 0, None, ch, 1, None)
            gdi.SetBkMode(self.dc, 1); gdi.GdiFlush()
            bw, bt = min(wide, self.bmp[0]), min(tall, self.bmp[1])
            src = np.frombuffer(ctypes.string_at(self.bits, self.bmp[0] * self.bmp[1] * 4), np.uint8).reshape(self.bmp[1], self.bmp[0], 4)
            o, d = self.outline, self.drop
            if bt - o > o and bw - d - o > o:
                s = src[o:bt - o, o:bw - d - o, :3].astype(np.float64)
                rgba[o:bt - o, o:bw - d - o, :3] = src[o:bt - o, o:bw - d - o, :3]
                rgba[o:bt - o, o:bw - d - o, 3] = (s[..., 0] * 0.34 + s[..., 1] * 0.55 + s[..., 2] * 0.11).astype(np.uint8)
            if self.drop and tall: rgba[tall - 1] = 0
        effects(rgba, self.drop, self.outline, self.blur, self.scanlines, self.rotary)
        self._cells[ch] = rgba
        return rgba

def _grow(mask, r):
    """A boolean picture grown by r px each way (a square: rows then columns), outside it nothing."""
    h, w = mask.shape
    out = np.zeros_like(mask)
    for d in range(-r, r + 1):                                   # along rows
        if abs(d) >= w: continue
        out[:, max(0, d):w + min(0, d)] |= mask[:, max(0, -d):w - max(0, d)]
    rows = np.zeros_like(mask)
    for d in range(-r, r + 1):                                   # then columns
        if abs(d) >= h: continue
        rows[max(0, d):h + min(0, d)] |= out[max(0, -d):h - max(0, d)]
    return rows

def effects(rgba, drop, outline, blur, scanlines, rotary):
    """The game's font effects, in its order, on an RGBA cell (height x width x 4) in place."""
    h, w = rgba.shape[:2]
    if drop and h > drop and w > drop:                          # clear pixels take the alpha of the one up-left
        src = rgba[:h - drop, :w - drop, 3].copy()
        tgt = rgba[drop:, drop:]
        clear = tgt[..., 3] == 0
        tgt[clear] = 0; tgt[..., 3][clear] = src[clear]
    if outline:                                                 # any lit neighbour with colour: this clear pixel goes black
        lit = np.all(rgba != 0, axis=2)
        hit = _grow(lit, outline) & (rgba[..., 3] == 0)
        rgba[hit] = (0, 0, 0, 255)
    if blur:                                                    # on alpha only; anything lit becomes white
        sigma = 0.683 * blur
        dist = [float(ctypes.c_float(1.0 / math.sqrt(2 * 3.14 * sigma * sigma) * math.pow(2.7, -(v - blur) ** 2 / (2 * sigma * sigma))).value) for v in range(2 * blur + 1)]
        for horizontal in (True, False):
            A = rgba[..., 3].astype(np.float64)
            if not horizontal: A = A.T                          # (rows of A: the line blurred along)
            n_in, n_out = A.shape
            res = np.zeros((n_in, n_out), np.int64)
            for p in range(n_out):
                off, nv = 0, 2 * blur + 1
                if p < blur: off = blur - p; nv -= off
                if p >= n_out - blur: nv = n_out - (p - off)
                nv = min(nv, n_out - (p + off - blur))
                acc = np.zeros(n_in)
                for k in range(nv): acc += dist[off + k] * A[:, p + off - blur + k]
                res[:, p] = np.minimum(255, acc.astype(np.int64))
            if not horizontal: res = res.T
            rgba[...] = 0
            on = res > 0
            rgba[on] = 255; rgba[..., 3][on] = res[on]
    if scanlines >= 2:
        rows = np.arange(h) % scanlines != 0
        rgba[rows, :, :3] = (rgba[rows, :, :3] * 0.7).astype(np.uint8)
    if rotary and h:
        rgba[int(h * 0.5)] = (127, 127, 127, 255)

def layout(font, text):
    """[(x, char)] where each letter's cell goes, and the line's width (the game's DrawPrintText). Every character is
    drawn, spaces too (a blank cell, but it takes the rotary line and an underline). A letter's cell goes at pen + a,
    an underlined one's at the pen (minus a when smoothed); measured 2026-10-12."""
    out, total = [], 0
    under = getattr(font, 'underline', False)
    for ch in text:
        a, b, c = font.abc(ch)
        out.append((total + (font.offset(ch) if under else math.floor(a + 0.6)), ch))
        total += math.floor(a + b + c + 0.6)
    return out, total

LIN = np.array([(v / 255) ** 2.2 for v in range(256)])                  # (the text colour and the letters, read as 2.2)
BACK = np.array([v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in np.arange(256) / 255])   # (what's behind: sRGB)

def srgb(v):
    """Linear light to the screen's value, as the game writes it: the sRGB curve (it reads colours as gamma 2.2).
    Measured: text colour 255 170 60 shows as 255 171 57 (2026-10-12 shots)."""
    return np.where(v <= 0.0031308, 12.92 * v, 1.055 * np.power(np.maximum(v, 0), 1 / 2.4) - 0.055)

def draw_np(arr, font, text, x, y, colour=(255, 255, 255, 255), copies=1):
    """Text onto an RGB array (height x width x 3, uint8) at (x, y), the game's way: the cell times the colour, blended
    in linear light (the game's blending, measured: README), added instead if the font is additive. copies: how many
    times the game draws it over itself (a server text is drawn once per send it still holds: README). The line's width."""
    H_, W_ = arr.shape[:2]
    cl, ca = LIN[list(colour[:3])], colour[3] / 255
    placed, width = layout(font, text)
    for cx, ch in placed:
        cell = font.cell(ch)
        h, b = cell.shape[:2]
        X, Y = x + cx, y
        xs, ys, xe, ye = max(0, -X), max(0, -Y), min(b, W_ - X), min(h, H_ - Y)
        if xe <= xs or ye <= ys: continue
        c = cell[ys:ye, xs:xe]
        al = c[..., 3] / 255 * ca
        lit = al > 0
        if not lit.any(): continue
        region = arr[Y + ys:Y + ye, X + xs:X + xe]
        dst, src = BACK[region], LIN[c[..., :3]] * cl
        if font.additive: out = np.minimum(1.0, dst + src * (al * copies)[..., None])
        else:
            keep = ((1 - al) ** copies)[..., None]              # (copies on top of each other: the same pixel each time)
            out = dst * keep + src * (1 - keep)
        region[lit] = np.rint(255 * srgb(out[lit])).astype(np.uint8)
    return width

# ---- bitmap fonts -------------------------------------------------------------------------------------------------
# vgui's bitmap font (CBitmapFont in CS:S x64 vguimatsurface.dll, read 2026-10-10). A .vbf: "VFNT", version 3, shorts
# page width, page height, max char width, max char height, flags, ascent, glyph count, a 256-byte table char -> glyph,
# then per glyph shorts x, y, w, h (its rectangle on the page), a, b, c. The page is the texture
# vgui/fonts/<the .vbf's file name, lower-case>. The game scales by the entry's scalex/scaley: ABC widths, height and
# ascent truncated after scaling, the line spaced by the unscaled-then-multiplied widths (a*sx + b*sx + c*sx, rounded
# as for any font), each letter's rectangle stretched to b by the height. Of the scheme's flags only additive counts.
VBF_FLAGS = {'italic': 0x2, 'outline': 0x4, 'dropshadow': 0x8, 'blur': 0x10, 'scanlines': 0x20, 'antialias': 0x40}
f32 = lambda v: struct.unpack('<f', struct.pack('<f', v))[0]

# VTF image formats: raw ones (PIL mode, raw mode, bytes per pixel) and DXT ones (PIL bcn number, bytes per 4x4 block)
VTF_RAW = {0: ('RGBA', 'RGBA', 4), 1: ('RGBA', 'ABGR', 4), 2: ('RGB', 'RGB', 3), 3: ('RGB', 'BGR', 3), 5: ('L', 'L', 1),
           6: ('LA', 'LA', 2), 8: ('L', 'L', 1), 11: ('RGBA', 'ARGB', 4), 12: ('RGBA', 'BGRA', 4), 16: ('RGB', 'BGRX', 4)}
VTF_DXT = {13: (1, 8), 20: (1, 8), 14: (2, 16), 15: (3, 16)}

def read_vtf(path, data=None):
    """A .vtf's full-size picture (first frame) as RGBA, and whether it's point sampled. data: its bytes, if they're
    not in a file of their own (a VPK's)."""
    data = data if data is not None else open(path, 'rb').read()
    if data[:4] != b'VTF\0': raise ValueError(f'{os.path.basename(path)} is not a VTF')
    w, h, flags, frames = struct.unpack_from('<HHIH', data, 16)
    fmt = struct.unpack_from('<i', data, 52)[0]
    if fmt in VTF_DXT: size = ((w + 3) // 4) * ((h + 3) // 4) * VTF_DXT[fmt][1]
    elif fmt in VTF_RAW: size = w * h * VTF_RAW[fmt][2]
    else: raise ValueError(f'{os.path.basename(path)}: VTF format {fmt} is not read here')
    # ponytail: the full-size level is the file's last block (mips go small to big); cube maps and volumes not handled
    raw = data[len(data) - max(1, frames) * size:][:size]
    if fmt in VTF_DXT: return Image.frombytes('RGBA', (w, h), raw, 'bcn', VTF_DXT[fmt][0]), bool(flags & 1)
    mode, rawmode, _ = VTF_RAW[fmt]
    img = Image.frombytes(mode, (w, h), raw, 'raw', rawmode)
    if fmt == 8: a, img = img, Image.new('RGBA', (w, h), (255, 255, 255, 255)); img.putalpha(a)   # A8: white, alpha
    return img.convert('RGBA'), bool(flags & 1)

class VPK:
    """A game VPK (its _dir.vpk): its file list, and any file's bytes."""
    def __init__(self, dir_path):
        d = self.dir = open(dir_path, 'rb').read()
        _, ver, tree = struct.unpack_from('<III', d, 0)
        pos = 12 if ver == 1 else 28                            # (version 2: four more sizes in the header)
        self.base, self.data_at, self.files = dir_path[:-len('_dir.vpk')], pos + tree, {}
        def name():
            nonlocal pos
            end = d.index(b'\0', pos); out = d[pos:end].decode('latin-1'); pos = end + 1
            return out
        while (ext := name()):                                  # extension, then path, then file name, each list ''-ended
            while (path := name()):
                while (file := name()):
                    _, pre, arc, off, size, _ = struct.unpack_from('<IHHIIH', d, pos); pos += 18
                    full = ('' if path == ' ' else path + '/') + file + ('' if ext == ' ' else '.' + ext)
                    self.files[full.lower()] = (pos, pre, arc, off, size); pos += pre

    def read(self, name):
        at, pre, arc, off, size = self.files[name.lower()]
        head = self.dir[at:at + pre]                            # (a file's first bytes can be in the directory)
        if arc == 0x7FFF: return head + self.dir[self.data_at + off:self.data_at + off + size]
        with open(f'{self.base}_{arc:03d}.vpk', 'rb') as f:
            f.seek(off); return head + f.read(size)

class BitmapFont:
    """A .vbf + its page picture, as the game draws it: the same face/height/abc/cell/additive as Win32Font."""
    def __init__(self, vbf, vtf, scalex=1.0, scaley=1.0, flags=0):
        f = open(vbf, 'rb').read()
        if f[:4] != b'VFNT': raise ValueError(f'{os.path.basename(vbf)} is not a bitmap font')
        _, _, _, mh, _, _, n = struct.unpack_from('<7h', f, 8)
        if n <= 0 or len(f) < 0x116 + 14 * n: raise ValueError(f'{os.path.basename(vbf)}: no letters in it')
        self.table = f[0x16:0x116]
        self.glyphs = [struct.unpack_from('<7h', f, 0x116 + 14 * i) for i in range(n)]
        self.page, self.point = read_vtf(vtf)
        self.sx, self.sy = f32(scalex), f32(scaley)
        self.face, self.flags = os.path.splitext(os.path.basename(vbf))[0], flags | FONTFLAG['bitmap']
        self.height = int(mh * self.sy)
        self.additive = bool(flags & FONTFLAG['additive'])
        self._cells = {}

    def close(self): pass

    def glyph(self, ch):
        o = ord(ch)
        return self.glyphs[self.table[o] if o < 256 and self.table[o] < len(self.glyphs) else 0]

    def abc(self, ch):
        """Scaled, each truncated to whole px (measured in game 2026-10-17: at x2.25 the letters advance by
        int(a) + int(b) + int(c), not the sum's fractions); the cell is b + 2 wide."""
        a, b, c = self.glyph(ch)[4:]
        return int(f32(a * self.sx)), int(f32(b * self.sx)), int(f32(c * self.sx))

    def cell(self, ch):
        """The letter's rectangle on the page stretched to int(b) + 2 by the height + 2, as the game draws it (measured
        in game 2026-10-17: a bitmap letter comes out 2 px wider and taller than its rectangle, point sampled)."""
        if ch not in self._cells:
            x, y, w, h, a, b, c = self.glyph(ch)
            size = (max(0, int(f32(b * self.sx))) + 2, max(0, self.height) + 2)
            if min(w, h, *size) <= 0: self._cells[ch] = np.zeros((size[1], size[0], 4), np.uint8)
            else:
                # ponytail: Pillow's bilinear clamps at the rectangle's edge where the card samples its neighbours
                if self.point:                                  # (texel floor((j + 0.5) * w / W), a tie going down, as the card does)
                    src = np.asarray(self.page.crop((x, y, x + w, y + h)))
                    ix = np.clip(np.floor((np.arange(size[0]) + 0.5) * w / size[0] - 1e-4).astype(int), 0, w - 1)
                    iy = np.clip(np.floor((np.arange(size[1]) + 0.5) * h / size[1] - 1e-4).astype(int), 0, h - 1)
                    self._cells[ch] = src[iy][:, ix].copy()
                else:                                           # (bilinear as the card does it, measured in game 2026-10-17:
                    # each channel on its own, colour in linear light (2.2), the page's own texels round the rectangle)
                    src = np.asarray(self.page.crop((x - 1, y - 1, x + w + 1, y + h + 1))).astype(np.float64)
                    src[..., :3] = LIN[src[..., :3].astype(int)]
                    u = (np.arange(size[0]) + 0.5) * w / size[0] + 0.5; v = (np.arange(size[1]) + 0.5) * h / size[1] + 0.5
                    u0, v0 = np.clip(np.floor(u).astype(int), 0, w + 1), np.clip(np.floor(v).astype(int), 0, h + 1)
                    u1, v1 = np.minimum(u0 + 1, w + 1), np.minimum(v0 + 1, h + 1)
                    fu, fv = (u - np.floor(u))[None, :, None], (v - np.floor(v))[:, None, None]
                    out = (src[v0][:, u0] * (1 - fu) + src[v0][:, u1] * fu) * (1 - fv) + (src[v1][:, u0] * (1 - fu) + src[v1][:, u1] * fu) * fv
                    out[..., :3] = 255 * out[..., :3] ** (1 / 2.2)
                    self._cells[ch] = np.clip(np.rint(out), 0, 255).astype(np.uint8)
        return self._cells[ch]

BAKE = [chr(c) for c in [*range(0x20, 0x7F), *range(0xA0, 0x100)]]     # (glyph 0 is the space: unknowns draw as one)

def max_round(im, r):
    """Each pixel of a grey picture the brightest within r of it (a disc, so curves keep round outlines; outside the
    picture 0). Rows first, a px wider each step, then every row of the disc at its own width: about 2r steps."""
    a = np.asarray(im, np.uint8); R = int(r); h, w = a.shape
    p = np.zeros((h + 2 * R, w + 2 * R), np.uint8); p[R:R + h, R:R + w] = a
    rows = [p]                                                  # rows[k][y, x]: the brightest of p[y, x-k .. x+k]
    for k in range(1, R + 1):
        n = rows[-1].copy()
        n[:, k:] = np.maximum(n[:, k:], p[:, :-k]); n[:, :-k] = np.maximum(n[:, :-k], p[:, k:])
        rows.append(n)
    out = np.zeros_like(p)
    for dy in range(-R, R + 1):
        src = rows[int(math.sqrt(max(0.0, r * r - dy * dy)))]
        if dy >= 0: out[:out.shape[0] - dy] = np.maximum(out[:out.shape[0] - dy], src[dy:])
        else: out[-dy:] = np.maximum(out[-dy:], src[:dy])
    return Image.fromarray(out[R:R + h, R:R + w])

def restyle(im, style):
    """A cell's colours changed: the letter's pixels (lit: white, or grey on scan lines) to style['letter'], the
    game-style outline and shadow's (black) to style['edge'], each (r, g, b, opacity 0-1)."""
    a = np.array(im).astype(np.float64)
    v = a[..., :3].max(axis=2)
    letter = v > 0
    lc, ec = np.array(style['letter'][:3], float), np.array(style['edge'][:3], float)
    rgb = np.where(letter[..., None], lc * (v / 255)[..., None], ec)
    alpha = a[..., 3] * np.where(letter, style['letter'][3], style['edge'][3])
    return Image.fromarray(np.rint(np.dstack([rgb, alpha])).astype(np.uint8), 'RGBA')

STYLE = {'letter': (255, 255, 255, 1.0), 'edge': (0, 0, 0, 1.0), 'box': (0, 0, 0, 1.0)}

def bake(font, base, smooth=0, chars=BAKE, box=None, style=None, spacing=0, even=False, digits=True, centre=False,
         sharp=0, trim=0):
    """A bitmap font (base.vbf + base.vtf) of a Win32Font's letters as the game draws them, its effects in. smooth: a
    smooth outline that many px wide drawn under the letters: black under every pixel near a letter, faint edge pixels
    too, so nothing shows between letter and outline (the game's own Outline leaves those uncovered). Spaced like the
    Win32 font: an entry with scale 1 draws it the same (the outline widens each cell on both sides, not the line).
    box: a solid black box behind the text, that many px above and below the letters: each letter's cell is its whole
    advance wide, so the cells meet into one box (letter pixels outside their advance are cut; a space is a gap in it). style: colours and opacity of the letters, their outline and shadow (the
    smooth one too) and the box, as STYLE (the game multiplies them by the text colour). chars: which letters (fewer for
    a quick look). spacing: px added after every letter; even: instead, every letter's ink (its outline too) exactly
    spacing px from the next; digits: and the digits all one width (a changing number doesn't jiggle); centre: brackets
    moved up or down to sit centred on the digits; sharp: 0-100, how narrow the soft (see-through) edge is: a server text
    drawn twice over itself darkens every see-through pixel, so a narrower edge pulses less; 100: each pixel solid or
    clear, no pulsing at all but a stair-stepped edge (the letters' soft edges stay, on the outline); trim: the digits'
    one width that many px less than the widest digit's (the wider ones then reach into the gaps). smooth can be a fraction (1.5). Returns (glyph count, page size)."""
    P, pad = math.ceil(smooth), box or 0
    st = {**STYLE, **(style or {})}
    plain = st == STYLE
    H = font.height + 2 * P + 2 * pad
    cells = []
    for ch in [' '] + sorted({c for c in chars if c != ' ' and ord(c) < 256}):
        a, b, c = font.abc(ch)
        c += spacing
        lined = font.underline or font.rotary                  # (a space's cell: blank but for these lines)
        im = Image.fromarray(font.cell(ch)) if b > 0 and (lined or not ch.isspace()) else None
        a0 = font.offset(ch) if font.underline else a          # (where the live font puts the cell)
        if im and not plain: im = restyle(im, st)
        if im and P:
            outl = Image.new('RGBA', (im.width - 2 + 2 * P, font.height + 2 * P), (0, 0, 0, 0)); outl.paste(im, (P, P))
            W_, H_ = outl.size
            edge = outl.getchannel('A').resize((W_ * 4, H_ * 4), Image.BILINEAR).point(lambda v: 255 if v >= 128 else 0)
            ring = max_round(edge, 4 * smooth)                  # (from the letter's half-covered edge: as wide both sides)
            under = Image.new('RGBA', (W_, H_), (*st['edge'][:3], 0))
            under.putalpha(ring.resize((W_, H_), Image.BOX).point(lambda v: round(v * st['edge'][3])))
            im = Image.alpha_composite(under, outl)
        if im and sharp:                                       # (alpha steeper about its middle: k = 1 / (1 - sharp))
            px = np.asarray(im).copy(); al = px[..., 3].astype(np.float64)
            px[..., 3] = np.where(al >= 128, 255, 0) if sharp >= 100 else np.clip(np.rint((al - 127.5) * 100 / (100 - sharp) + 127.5), 0, 255)
            im = Image.fromarray(px)
        if box is not None:                                     # the whole advance, black, the letter on it
            adv = a + b + c
            cell = Image.new('RGBA', (max(0, adv), H), (*st['box'][:3], round(255 * st['box'][3])))
            if im and adv > 0:
                layer = Image.new('RGBA', cell.size, (0, 0, 0, 0)); layer.paste(im, (a0 - P, pad))
                cell = Image.alpha_composite(cell, layer)
            cells.append((ch, cell if adv > 0 else None, (0, max(0, adv), 0) if adv > 0 else (a, b, c)))
        else:
            cells.append((ch, im, (a0 - P, a + b + c - a0 + P, 0) if im else (a, b, c)))   # (b + c: the advance left)
    def rows(im):                                               # (the rows its ink is on: top, bottom + 1)
        r = np.nonzero(np.asarray(im.getchannel('A')).max(axis=1))[0] if im else []
        return (int(r[0]), int(r[-1]) + 1) if len(r) else None
    mid = [sum(r) / 2 for ch, im, _ in cells if ch in '0123456789' and (r := rows(im))]
    if centre and mid and box is None:
        mid = sum(mid) / len(mid)
        for i, (ch, im, abc) in enumerate(cells):
            if ch in '()[]{}' and (r := rows(im)):
                moved = Image.new('RGBA', im.size, (0, 0, 0, 0)); moved.paste(im, (0, round(mid - sum(r) / 2)))
                cells[i] = (ch, moved, abc)
    if even and box is None:
        ink = {}
        for ch, im, _ in cells:
            cols = np.nonzero(np.asarray(im.getchannel('A')).max(axis=0))[0] if im else []
            if len(cols): ink[ch] = (int(cols[0]), int(cols[-1]) + 1)
        digit = max((r - l for ch, (l, r) in ink.items() if ch in '0123456789'), default=0) - trim
        for i, (ch, im, abc) in enumerate(cells):
            if ch not in ink: continue
            l, r = ink[ch]; room = digit if digits and ch in '0123456789' else r - l
            a = (room - (r - l)) // 2
            cells[i] = (ch, im.crop((l, 0, r, im.height)), (a, room + spacing - a, 0))
    for PW in (256, 512, 1024, 2048, 4096):                     # the smallest page they fit, at most twice as tall
        x = y = 2; spots = []
        for ch, im, _ in cells:
            w = im.width + 2 if im else 0                       # (+ 2: the room the game stretches the letter into)
            if x + w + 2 > PW: x, y = 2, y + H + 4
            spots.append((x, y)); x += w + 2
        PH = 1 << math.ceil(math.log2(y + H + 4))
        if PH <= PW: break
    page = Image.new('RGBA', (PW, PH), (0, 0, 0, 0))
    glyphs, table = [], bytearray(256)
    for i, ((ch, im, (a, b, c)), (x, y)) in enumerate(zip(cells, spots)):
        if im:                                                  # (b: the picture's whole width, so it isn't squeezed;
            page.paste(im, (x, y)); glyphs.append((x, y, im.width + 2, H + 2, a, im.width, b + c - im.width))   # c: same spacing)
        else: glyphs.append((x, y, 0, H, a, b, c))
        table[ord(ch)] = i
    flags = sum(v for k, v in VBF_FLAGS.items() if {'italic': font.flags & 1, 'outline': font.outline or P,
                'dropshadow': font.drop, 'blur': font.blur, 'scanlines': font.scanlines, 'antialias': font.aa}[k])
    hdr = b'VFNT' + struct.pack('<i7h', 3, PW, PH, max(g[2] for g in glyphs), H, flags, font.ascent + P + pad, len(glyphs))
    with open(base + '.vbf', 'wb') as f: f.write(hdr + bytes(table) + b''.join(struct.pack('<7h', *g) for g in glyphs))
    # VTF 7.2, BGRA8888, one level: clamped S/T, point sampled, no mipmaps or LOD, 8-bit alpha
    vtf = bytearray(80)
    vtf[0:4] = b'VTF\0'; struct.pack_into('<IIIHHI', vtf, 4, 7, 2, 80, PW, PH, 0x1 | 0x4 | 0x8 | 0x100 | 0x200 | 0x2000)
    struct.pack_into('<H', vtf, 24, 1); struct.pack_into('<fI', vtf, 48, 1.0, 12)
    vtf[56] = 1; struct.pack_into('<IH', vtf, 57, 0xFFFFFFFF, 0); struct.pack_into('<H', vtf, 63, 1)
    r, g, b_, a_ = page.split()
    with open(base + '.vtf', 'wb') as f: f.write(bytes(vtf) + Image.merge('RGBA', (b_, g, r, a_)).tobytes())
    return len(glyphs), (PW, PH)

def _find_at(items, key):
    return next((it for it in items if it[0].lower() == key.lower()), None)

def _root_at(text):
    return next((v for k, v, *_ in parse_kv_at(text) if isinstance(v, list)), [])

def has_fonts(text):
    b = _find_at(_root_at(text), 'Fonts')
    return bool(b and isinstance(b[1], list))

def block_text(text, font):
    """A font's block in a scheme file as it's written: (its first line's number, the text from the line with its name
    to the line before the next font's name, or Fonts' closing brace), or None if the file hasn't it."""
    fonts = _find_at(_root_at(text), 'Fonts')
    if not fonts or not isinstance(fonts[1], list): return None
    items = fonts[1]
    i = next((n for n, it in enumerate(items) if it[0].lower() == font.lower() and isinstance(it[1], list)), None)
    if i is None: return None
    start = text.rfind('\n', 0, items[i][2]) + 1
    end = text.rfind('\n', 0, items[i + 1][2] if i + 1 < len(items) else fonts[3] - 1) + 1
    if end <= start: return text.count('\n', 0, items[i][2]) + 1, text[items[i][2]:items[i][3]]   # (a block on one line)
    return text.count('\n', 0, start) + 1, text[start:end]

def has_block(text, font):
    b = _find_at(_root_at(text), 'Fonts')
    b = b and isinstance(b[1], list) and _find_at(b[1], font)
    return bool(b and isinstance(b[1], list))

def set_font_entry(text, font, key, entry, before=None):
    """A scheme file's text with the font's entry `key` written as `entry` (a dict), in place if the file has it, else
    put before the entry `before` (the game uses a font's first entry that fits), else added at the end of the font's
    block (the block too, at the end of Fonts, if it has none). The rest is kept as it was, byte for byte."""
    plain(font, key, *entry.keys(), *entry.values())
    nl = '\r\n' if '\r\n' in text else '\n'
    def indent(at):
        line = text.rfind('\n', 0, at) + 1
        return re.match(r'[ \t]*', text[line:]).group(0)
    def lines(ind, rows): return nl.join(ind + r if r else r for r in rows)
    body = entry_text(entry, key).rstrip('\n').split('\n')
    fonts = _find_at(_root_at(text), 'Fonts')
    if not fonts or not isinstance(fonts[1], list): raise ValueError('it has no Fonts block')
    block = _find_at(fonts[1], font)
    if block and isinstance(block[1], list):
        had = _find_at(block[1], key)
        if had:
            ind = indent(had[2])
            return text[:had[2]] + body[0] + nl + lines(ind, body[1:]) + text[had[3]:]
        nxt = before and _find_at(block[1], before)
        if nxt:
            ind = indent(nxt[2])
            return text[:nxt[2]] + body[0] + nl + lines(ind, body[1:]) + nl + ind + text[nxt[2]:]
        close, ind = block[3] - 1, indent(block[2]) + '\t'
    else:
        close, ind = fonts[3] - 1, indent(fonts[2]) + '\t'
        body = [f'"{font}"', '{'] + ['\t' + r for r in body] + ['}']
    at = text.rfind('\n', 0, close) + 1                       # (the closing brace's line: the entry goes above it)
    if text[at:close].strip(): return text[:close] + nl + lines(ind, body) + nl + text[close:]   # (a "{ ... }" on one line)
    return text[:at] + lines(ind, body) + nl + text[at:]

def write_atomic(path, data):
    """Bytes to a file all at once: written beside it, then put in its place (a crash leaves the old file whole; a
    failed replace leaves no temp file)."""
    tmp = path + '.fonttester-tmp'
    with open(tmp, 'wb') as f: f.write(data)
    try: os.replace(tmp, path)
    except OSError: os.remove(tmp); raise

def plain(*values):
    """A quote or a line break in a key or value would break the scheme file (KeyValues has no escapes)."""
    for v in values:
        if any(c in str(v) for c in '"\r\n'): raise ValueError(f'{v!r}: a quote or line break can\'t go in a scheme file')

def add_list_line(text, block, key, value, has=None):
    """A scheme file's text with "key" "value" in the list block (BitmapFontFiles, CustomFontFiles; a new one before
    Fonts if it has none). has(the block's items) -> True: it's there already, nothing changed. The rest is kept."""
    plain(key, value)
    nl = '\r\n' if '\r\n' in text else '\n'
    indent = lambda at: re.match(r'[ \t]*', text[text.rfind('\n', 0, at) + 1:]).group(0)
    root, row = _root_at(text), f'"{key}"\t"{value}"'
    b = _find_at(root, block)
    if b and isinstance(b[1], list):
        if has and has(b[1]): return text
        close = b[3] - 1                                        # (its closing brace)
        at = text.rfind('\n', 0, close) + 1
        if text[at:close].strip(): return text[:close] + f' {row} ' + text[close:]   # (a block on one line)
        return text[:at] + indent(b[2]) + '\t' + row + nl + text[at:]
    f = _find_at(root, 'Fonts')
    if not f: raise ValueError(f'no Fonts block to put {block} before')
    at = text.rfind('\n', 0, f[2]) + 1
    if text[at:f[2]].strip(): return text[:f[2]] + f'{block} {{ {row} }} ' + text[f[2]:]   # (Fonts not first on its line)
    ind = indent(f[2])
    return text[:at] + f'{ind}{block}{nl}{ind}{{{nl}{ind}\t{row}{nl}{ind}}}{nl}' + text[at:]

def _strings(items):
    for k, v, *_ in items:
        yield k
        yield from (_strings(v) if isinstance(v, list) else [v])

def add_bitmap_file(text, name, rel):
    """BitmapFontFiles: "name" "rel" (nothing changed if the name is there)."""
    return add_list_line(text, 'BitmapFontFiles', name, rel, lambda items: any(k.lower() == name.lower() for k, *_ in items))

def add_custom_font(text, rel, key):
    """CustomFontFiles: "key" "rel" (nothing changed if rel is listed)."""
    return add_list_line(text, 'CustomFontFiles', key, rel,
                         lambda items: any(rel.lower() == v.replace('\\', '/').lower() for v in _strings(items)))

def font_file(face, weight=400, italic=False):
    """The font file Windows draws this face with (the HUD's own if it's loaded, else the PC's): (bytes, extension)."""
    if not face_exists(face): raise ValueError(f'no font {face!r} on this PC')
    dc = gdi.CreateCompatibleDC(None)
    hf = gdi.CreateFontA(48, 0, 0, 0, weight, int(italic), 0, 0, 1, 0, 0, 4, 0, face.encode('mbcs', 'replace'))
    gdi.SelectObject(dc, hf)
    data, ext = None, None
    for table, kind in ((struct.unpack('<I', b'ttcf')[0], '.ttc'), (0, None)):     # (a collection: the whole file)
        n = gdi.GetFontData(dc, table, 0, None, 0)
        if n and n != 0xFFFFFFFF:
            buf = ctypes.create_string_buffer(n); gdi.GetFontData(dc, table, 0, buf, n)
            data = buf.raw; ext = kind or ('.otf' if data[:4] == b'OTTO' else '.ttf'); break
    gdi.DeleteObject(hf); gdi.DeleteDC(dc)
    if not data: raise ValueError(f'{face} has no font file to copy')
    return data, ext

# ---- schemes ------------------------------------------------------------------------------------------------------

CONDS = {'WIN32': True, 'WINDOWS': True}
def _cond(expr):
    """[$WIN32], [!$OSX], [$WIN32||$X360] ... on a Windows PC."""
    expr = expr.strip('[]').replace(' ', '').upper()
    return any(all((not CONDS.get(t[2:], False)) if t.startswith('!$') else CONDS.get(t[1:], False)
                   for t in part.split('&&')) for part in expr.split('||'))

TOKEN = re.compile(r'"([^"]*)"|(\[[^\]]*\])|(\{)|(\})|(//[^\n]*)|([^\s{}"]+)')

def parse_kv_at(text):
    """KeyValues text: [(key, value or list, start, end)] in order, start and end spanning the key to the end of its
    value (a block: its "}"); conditions applied; '#base' lines kept as ('#base', file, ...)."""
    bom = 3 if text.startswith('\xef\xbb\xbf') else 1 if text.startswith('\ufeff') else 0   # (UTF-8's mark)
    toks = [m for m in TOKEN.finditer(text, bom) if m.group(5) is None]
    pos = 0
    def tok():
        nonlocal pos
        m = toks[pos]; pos += 1
        return ('cond', m.group(2)) if m.group(2) else ('{', None) if m.group(3) else ('}', None) if m.group(4) else ('str', m.group(1) or m.group(6) or '')
    def block():
        nonlocal pos
        items = []
        while pos < len(toks):
            start = toks[pos].start()
            kind, key = tok()
            if kind == '}': break
            if kind != 'str': continue
            if pos >= len(toks): break
            kind2, val = tok()
            if kind2 == 'cond':                                 # a condition on the key, before its block
                if pos >= len(toks): break
                kind2, val = tok()
                ok = _cond(toks[pos - 2].group(2))
            else: ok = True
            if kind2 == '{': val = block()
            elif kind2 != 'str': continue
            end = toks[pos - 1].end()
            if pos < len(toks) and toks[pos].group(2):
                ok = ok and _cond(toks[pos].group(2)); pos += 1
            if ok: items.append((key, val, start, end))
        return items
    return block()

def parse_kv(text):
    """KeyValues text: [(key, value or list)] in order; conditions applied; '#base' lines kept as ('#base', file)."""
    plain = lambda items: [(k, plain(v) if isinstance(v, list) else v) for k, v, *_ in items]
    return plain(parse_kv_at(text))

def find(items, key):
    for k, v in items:
        if k.lower() == key.lower(): return v
    return None

def merge(mine, base):
    """#base: the base file's keys fill in what this file hasn't, recursing into blocks both have."""
    out = list(mine)
    for k, v in base:
        have = [i for i, (k2, _) in enumerate(out) if k2.lower() == k.lower()]
        if not have: out.append((k, v))
        elif isinstance(v, list) and isinstance(out[have[0]][1], list):
            out[have[0]] = (out[have[0]][0], merge(out[have[0]][1], v))
    return out

def load_scheme(path, fallback_dirs=(), read=None, seen=None):
    """A scheme file with its #base files merged in: (items, every file read). read(path) -> text, else the file."""
    seen = (seen or set()) | {os.path.normcase(os.path.abspath(path))}   # (a #base back to a file already read: skipped)
    text = read(path) if read else open(path, encoding='latin-1').read()
    items = parse_kv(text)
    bases = [v for k, v in items if k.lower() == '#base' and isinstance(v, str)]
    root = next((v for k, v in items if isinstance(v, list)), [])
    files = [path]
    for b in bases:
        for d in [os.path.dirname(path), *fallback_dirs]:
            p = os.path.join(d, b)
            if os.path.normcase(os.path.abspath(p)) in seen: break
            if os.path.isfile(p):
                bi, bf = load_scheme(p, fallback_dirs, read, seen)
                root = merge(root, bi); files += bf; break
    return root, files

def atoi(v, d=0):
    """A whole number as the game reads it (C's atoi): the leading digits, "12px" is 12; none: d."""
    m = re.match(r'\s*[-+]?\d+', '' if v is None else str(v))
    return int(m.group(0)) if m else d

def atof(v, d=0.0):
    """A number as the game reads it (C's atof): "1.5x" is 1.5; none: d."""
    m = re.match(r'\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?', '' if v is None else str(v))
    return float(m.group(0)) if m else d

def yres_range(d):
    """An entry's (lo, hi) screen heights, or None: every screen."""
    lo, hi = (list(map(int, re.findall(r'-?\d+', d.get('yres', '')))) + [0, 0])[:2]
    return (lo, hi or lo) if lo else None

def font_entries(scheme, font):
    """A font's entries as the game has them, in order: [(key, dict)] (a repeated key in an entry: the first one)."""
    entries = find(find(scheme, 'Fonts') or [], font)
    if not isinstance(entries, list): return []
    def keys(e):                                               # (in the file's order)
        d = {}
        for kk, v in e:
            if not isinstance(v, list): d.setdefault(kk.lower(), v)
        return d
    return [(k, keys(e)) for k, e in entries if isinstance(e, list)]

def sized(d, screen_h, grow):
    """An entry's pixel sizes: (entry, tall, blur, scanlines, scalex, scaley). grow: proportional with no yres: tall,
    blur and scan lines by int(height / 480 * v), a bitmap's scales the same way on scale x 10000, and anti-aliasing on
    if tall changed (vgui2.dll, read 2026-10-10)."""
    d = dict(d)
    tall, blur, scan = (max(0, atoi(d.get(k))) for k in ('tall', 'blur', 'scanlines'))
    def scale(k):                                               # (each on its own, as atof: "1.5x" is 1.5)
        try: return f32(atof(d.get(k, '1')))
        except OverflowError: return 0.0
    sx, sy = scale('scalex'), scale('scaley')
    if grow:
        g = lambda v: int(screen_h / 480 * v)
        was = tall
        tall, blur, scan = g(tall), g(blur), g(scan)
        sx, sy = (f32(g(int(f32(v * f32(10000.0)))) * f32(0.0001)) for v in (sx, sy))
        if tall != was: d['antialias'] = '1'
    return d, min(tall, 255), blur, scan, sx, sy                # (255: vgui2's cap, measured in game 2026-10-12)

def fits(d, screen_h):
    """The game uses a font's first entry whose yres holds the screen height; one without yres fits every screen."""
    r = yres_range(d)
    return not r or r[0] <= screen_h <= r[1]

def current(entries, screen_h):
    """The entry the game uses at this screen height (dict), or {}."""
    return next((d for _, d in entries if fits(d, screen_h)), {})

def place(entries, screen_h, scales=False):
    """Where an entry made at this screen height goes: (key, yres or None, the entry to put it before or None). The
    game uses a font's first entry whose yres fits; one without yres fits every screen. scales (a font with one entry
    the game grows with the screen, CenterPrintText: more entries break it): that entry, in place. Otherwise a new entry
    from just above the last range that ends below this screen up to 9999, before the one used now, so it's used from
    here up."""
    cur = next((k for k, d in entries if fits(d, screen_h)), None)
    if scales: return (cur or (entries[0][0] if entries else '1')), None, None
    prev = max([r[1] for k, d in entries if (r := yres_range(d)) and r[1] < screen_h], default=0)
    key = f'{prev + 1}+'
    return key, f'{prev + 1} 9999', (cur if cur and cur.lower() != key.lower() else None)

def entry_text(d, label='1'):
    """A font entry as scheme text, its keys in the dict's order."""
    lines = [f'"{label}"', '{'] + [f'\t"{k}"\t\t"{v}"' for k, v in d.items()] + ['}']
    return '\n'.join(lines) + '\n'

def faces():
    """Every font face Windows has for this program (the HUD's own font files too, once loaded)."""
    names = set()
    def cb(lf, *_):
        n = ctypes.cast(lf, ctypes.POINTER(LOGFONTA)).contents.lfFaceName.decode('mbcs', 'replace')
        if n and not n.startswith('@'): names.add(n)
        return 1
    lf = LOGFONTA(); lf.lfCharSet = 1
    dc = gdi.CreateCompatibleDC(None)
    gdi.EnumFontFamiliesExA(dc, ctypes.byref(lf), ENUMPROC(cb), 0, 0)
    gdi.DeleteDC(dc)
    return sorted(names, key=str.lower)

def make_font(entry, bitmaps=None):
    """The font for an entry; bitmaps: {name, lower-case: (vbf, vtf)} from bitmap_font_files."""
    d, tall, blur, scan, sx, sy = entry[:6]
    flags = 0
    for k, f in FONTFLAG.items():
        if k not in ('blur',) and atoi(d.get(k)): flags |= f
    if flags & FONTFLAG['bitmap']:
        vbf, vtf = (bitmaps or {}).get(d.get('name', '').lower(), (None, None))
        if not vbf: raise ValueError(f'no {d.get("name", "")!r} in BitmapFontFiles')
        for p in (vbf, vtf):
            if not os.path.isfile(p): raise ValueError(f'{os.path.basename(p)} not found')
        return BitmapFont(vbf, vtf, sx, sy, flags)
    return Win32Font(d.get('name', ''), tall, atoi(d.get('weight')), blur, scan, flags)

def bitmap_font_files(schemes, game_dirs):
    """Every scheme's BitmapFontFiles (the game keeps one list): {name, lower-case: (vbf, vtf)}, each file from the
    first game folder that has it (else where the first one would have it: watched, so it shows once it's made)."""
    def where(rel):
        rel = rel.replace('/', os.sep)
        return next((p for p in (os.path.join(d, rel) for d in game_dirs) if os.path.isfile(p)), os.path.join(game_dirs[0], rel))
    out = {}
    for items in schemes:
        for name, rel in find(items, 'BitmapFontFiles') or []:
            if isinstance(rel, str) and name.lower() not in out:
                stem = os.path.splitext(os.path.basename(rel.replace('\\', '/')))[0].lower()
                out[name.lower()] = (where(rel), where(f'materials/vgui/fonts/{stem}.vtf'))
    return out

def custom_font_files(scheme, hud_dir):
    out = []
    for _, v in find(scheme, 'CustomFontFiles') or []:
        f = v if isinstance(v, str) else find(v, 'font')
        if f: out.append(os.path.join(hud_dir, f.replace('/', os.sep)))
    return out

_loaded = {}
def load_font_files(paths):
    """Add a HUD's font files for this process only (re-added when a file changes)."""
    for p in [p for p in _loaded if p not in paths]:            # (a HUD no longer open: its fonts gone again)
        gdi.RemoveFontResourceExW(p, 0x10, None); del _loaded[p]
    for p in paths:
        if not os.path.isfile(p): continue
        m = os.path.getmtime(p)
        if _loaded.get(p) == m: continue
        if p in _loaded: gdi.RemoveFontResourceExW(p, 0x10, None)
        gdi.AddFontResourceExW(p, 0x10, None); _loaded[p] = m

if __name__ == '__main__':
    # self-check: the effects behave as the game's, the scheme rules pick the right entry, a line draws
    cell = np.zeros((5, 5, 4), np.uint8); cell[2, 2] = (255, 255, 255, 20)               # one faint pixel
    effects(cell, 0, 1, 0, 0, False)
    assert cell[2, 2, 3] == 20 and cell[1, 1, 3] == 255, 'outline: black around even a faint pixel'
    cell = np.zeros((4, 4, 4), np.uint8); cell[1, 1] = (255, 255, 255, 200)
    effects(cell, 1, 0, 0, 0, False)
    assert tuple(cell[2, 2]) == (0, 0, 0, 200), 'drop shadow: down-right, same alpha'
    s = parse_kv('"S" { Fonts { "F" { "1" { "name" "Arial" "tall" "10" "yres" "1 600" } "2" { "name" "Arial" "tall" "12" "yres" "601 2000" } '
                 '"3" { "name" "Arial" "tall" "18" } } "G" { "1" { "name" "Arial" [$OSX] "name" "Tahoma" [!$OSX] "tall" "18" } } } }')[0][1]
    def fe(scheme, font, h, changes=None):                     # (the entry used at this screen, sized: as the app does it)
        d = {**current(font_entries(scheme, font), h), **(changes or {})}
        return sized(d, h, not yres_range(d))
    def draw(img, font, text, x, y, colour=(255, 255, 255, 255)):
        arr = np.array(img); w = draw_np(arr, font, text, x, y, colour); img.paste(Image.fromarray(arr)); return w
    assert fe(s, 'F', 1080)[1] == 12 and fe(s, 'F', 480)[1] == 10, 'yres'
    assert fe(s, 'G', 1440)[0]['name'] == 'Tahoma' and fe(s, 'G', 1440)[1] == 54, 'conditions, proportional'
    f = Win32Font('Arial', 30, 400, flags=FONTFLAG['antialias'] | FONTFLAG['outline'])
    img = Image.new('RGB', (300, 50), (40, 40, 40)); w = draw(img, f, 'Speed: 123', 5, 5)
    assert w > 100 and img.getpixel((5 + layout(f, 'S')[0][0][0] + 8, 5 + f.ascent - 10)) != (40, 40, 40), 'a line draws'
    assert fe(s, 'G', 1440, changes={'tall': '20', 'outline': '1'})[1] == 60, 'changes apply before sizing'
    assert 'Arial' in faces() and '"outline"' in entry_text({'name': 'Arial', 'outline': '1'}), 'faces, entry text'
    # proportional growth: anti-aliasing on, a bitmap's scale by height / 480 on scale x 10000
    assert fe(s, 'G', 1440)[0].get('antialias') == '1' and 'antialias' not in fe(s, 'F', 1080)[0]
    b = parse_kv('"S" { Fonts { "B" { "1" { "bitmap" "1" "name" "x" "scalex" "0.5" } } } }')[0][1]
    assert fe(b, 'B', 1440)[4:] == (f32(15000 * f32(0.0001)), f32(30000 * f32(0.0001))), fe(b, 'B', 1440)[4:]
    # a font baked to a bitmap draws the same as the Win32 font at scale 1, and the smooth outline keeps the spacing
    import atexit, shutil, tempfile
    tmp = tempfile.mkdtemp(); atexit.register(shutil.rmtree, tmp, True)
    n, _ = bake(f, os.path.join(tmp, 'a'))
    bf = BitmapFont(os.path.join(tmp, 'a.vbf'), os.path.join(tmp, 'a.vtf'))
    assert n == len(BAKE) and bf.height == f.height and layout(bf, 'Speed: 123') == layout(f, 'Speed: 123')
    img2 = Image.new('RGB', (300, 50), (40, 40, 40)); draw(img2, bf, 'Speed: 123', 5, 5)
    assert img2.tobytes() == img.tobytes(), 'baked bitmap draws as the Win32 font'
    bake(f, os.path.join(tmp, 'b'), smooth=1)
    bo = BitmapFont(os.path.join(tmp, 'b.vbf'), os.path.join(tmp, 'b.vtf'), 2.0, 2.0)
    assert bo.height == 2 * (f.height + 2) and layout(bo, 'AV')[1] == math.floor(2 * sum(f.abc('A')) + 0.6) + math.floor(2 * sum(f.abc('V')) + 0.6)
    assert bo.page.getpixel((1, 1))[3] == 0 and read_vtf(os.path.join(tmp, 'b.vtf'))[1], 'page read back, point sampled'
    n, _ = bake(f, os.path.join(tmp, 'c'), chars='Speed')
    assert n == 5 and layout(BitmapFont(os.path.join(tmp, 'c.vbf'), os.path.join(tmp, 'c.vtf')), 'Speed') == layout(f, 'Speed'), 'a few letters'
    uf = Win32Font('Arial', 30, 400, flags=FONTFLAG['antialias'] | FONTFLAG['underline'])
    bake(uf, os.path.join(tmp, 'u'), chars='QWj ')
    assert layout(BitmapFont(os.path.join(tmp, 'u.vbf'), os.path.join(tmp, 'u.vtf')), 'QW j') == layout(uf, 'QW j'), 'underlined: placed as live'
    uf.close()
    bake(f, os.path.join(tmp, 'sp'), smooth=1.5, chars='AB', spacing=3)
    assert layout(BitmapFont(os.path.join(tmp, 'sp.vbf'), os.path.join(tmp, 'sp.vtf')), 'AB')[1] == layout(f, 'AB')[1] + 6, 'spacing'
    bake(f, os.path.join(tmp, 'ev'), smooth=1, chars='(1)\u00b2', spacing=2, even=True, centre=True)   # (superscript 2: not a digit here)
    ev = BitmapFont(os.path.join(tmp, 'ev.vbf'), os.path.join(tmp, 'ev.vtf'))
    ink = {ch: np.nonzero(np.asarray(ev.cell(ch))[..., 3]) for ch in '(1'}
    assert abs((ink['('][0].min() + ink['('][0].max()) - (ink['1'][0].min() + ink['1'][0].max())) <= 2, 'brackets centred on the digits'
    bake(f, os.path.join(tmp, 'tr'), chars='0148', spacing=1, even=True)
    bake(f, os.path.join(tmp, 'tr2'), chars='0148', spacing=1, even=True, trim=2)
    adv = lambda n: sum(BitmapFont(os.path.join(tmp, n + '.vbf'), os.path.join(tmp, n + '.vtf')).abc('1'))
    assert adv('tr2') == adv('tr') - 2, 'trim: the digits 2 px narrower'
    bake(f, os.path.join(tmp, 'so'), smooth=1.5, chars='O%', sharp=100)
    so = BitmapFont(os.path.join(tmp, 'so.vbf'), os.path.join(tmp, 'so.vtf'))
    one, two = (np.full((40, 80, 3), 90, np.uint8) for _ in range(2))
    draw_np(one, so, 'O%', 2, 2, (255, 0, 0, 255), 1); draw_np(two, so, 'O%', 2, 2, (255, 0, 0, 255), 2)
    assert (one == two).all() and (one != 90).any(), 'sharp 100: drawn twice looks as drawn once'
    assert ev.abc('(')[0] == 0 and ev.abc('(')[0] + ev.abc('(')[1] + ev.abc('(')[2] == ink['('][1].max() + 1 + 2, 'even gaps'
    assert fe(b, 'B', 1440, changes={'yres': '1 10000'})[4] == f32(0.5), 'a yres change: drawn unscaled'
    sch = '"Scheme"\r\n{\r\n\tColors\r\n\t{\r\n\t}\r\n\tFonts\r\n\t{\r\n\t}\r\n}\r\n'
    one = add_bitmap_file(sch, 'Big', 'materials/vgui/fonts/big.vbf')
    two = add_bitmap_file(one, 'Small', 'materials/vgui/fonts/small.vbf')
    got = find(parse_kv(two)[0][1], 'BitmapFontFiles')
    assert got == [('Big', 'materials/vgui/fonts/big.vbf'), ('Small', 'materials/vgui/fonts/small.vbf')], got   # (new ones last)
    assert add_bitmap_file(two, 'big', 'x') == two and two.count('\n') == two.count('\r\n') and two.startswith(sch[:30])
    s2 = set_font_entry(two, 'Speed', '1', {'name': 'Arial', 'tall': '20'})
    s3 = set_font_entry(s2, 'Speed', '1', {'bitmap': '1', 'name': 'Big'})
    s4 = set_font_entry(s3, 'Speed', '2', {'name': 'Tahoma'})
    got = find(find(parse_kv(s4)[0][1], 'Fonts'), 'Speed')
    assert got == [('1', [('bitmap', '1'), ('name', 'Big')]), ('2', [('name', 'Tahoma')])], got
    bt = block_text('"S"\n{\n\tFonts\n\t{\n\t\t// a\n\t\tA\n\t\t{\n\t\t}\n\n\t\tB\n\t\t{\n\t\t}\n\t}\n}\n', 'A')
    assert bt == (6, '\t\tA\n\t\t{\n\t\t}\n\n'), bt
    assert block_text('"S" { Fonts { B { } } }', 'B')[0] == 1 and block_text('"S" { Fonts { } }', 'B') is None
    assert [k for k, _ in font_entries(parse_kv(s4)[0][1], 'speed')] == ['1', '2'], 'entries in place, the new one last'
    assert s4.startswith(two[:two.index('Fonts')]) and s4.count('\n') == s4.count('\r\n')
    assert parse_kv_at('"a" { "b" "c" }')[0][2:] == (0, 15), 'spans'
    dot = np.zeros((31, 31), np.uint8); dot[15, 15] = 200
    disc = np.asarray(max_round(Image.fromarray(dot), 6.5))
    yy, xx = np.mgrid[-15:16, -15:16]
    assert (disc == np.where(xx * xx + yy * yy <= 6.5 ** 2, 200, 0)).all(), 'max_round: a disc'
    bake(f, os.path.join(tmp, 'x'), smooth=1, chars='AVW', box=3)
    bx = BitmapFont(os.path.join(tmp, 'x.vbf'), os.path.join(tmp, 'x.vtf'))
    img3 = Image.new('RGB', (200, 60), (200, 0, 0)); w3 = draw(img3, bx, 'AVW', 5, 5)
    row = [img3.getpixel((x, 5 + bx.height // 2)) for x in range(5, 5 + w3)]
    assert bx.height == f.height + 2 + 6 and layout(bx, 'AVW')[1] == layout(f, 'AVW')[1] and (200, 0, 0) not in row, 'one black box, no gaps'
    hh = font_entries(parse_kv('"S" { Fonts { "H" { "600" { "tall" "13" "yres" "1 600" } "1080" { "tall" "23" "yres" "601 1080" } '
                               '"1440" { "tall" "30" "yres" "1081 1440" } "x" { "tall" "45" "yres" "1441 10000" } } } }')[0][1], 'H')
    assert place(hh, 1440) == ('1081+', '1081 9999', '1440') and place(hh, 2000) == ('1441+', '1441 9999', 'x'), 'yres from the last range below'
    assert place(hh[:1], 1440) == ('601+', '601 9999', None) and place([('1', {'tall': '18'})], 1440) == ('1+', '1 9999', '1')
    assert place([('1', {'tall': '18'})], 1440, scales=True) == ('1', None, None), 'one entry that grows: in place'
    t5 = set_font_entry(s4, 'Speed', '0+', {'name': 'X'}, before='2')
    assert [k for k, _ in find(find(next(v for k, v in parse_kv(t5) if isinstance(v, list)), 'Fonts'), 'Speed')] == ['1', '0+', '2'], 'before'
    t6 = add_custom_font(add_custom_font(two, 'resource/fonts/a.ttf', '1'), 'resource/fonts/a.ttf', '2')
    assert find(next(v for k, v in parse_kv(t6) if isinstance(v, list)), 'CustomFontFiles') == [('1', 'resource/fonts/a.ttf')]
    data, ext = font_file('Arial', 700)
    assert ext in ('.ttf', '.ttc') and len(data) > 10000, 'Arial Bold\'s file'
    cellim = Image.fromarray(f.cell('A'))
    assert restyle(cellim, STYLE).tobytes() == cellim.tobytes(), 'restyle: the default changes nothing'
    red = np.array(restyle(cellim, {**STYLE, 'letter': (255, 0, 0, 0.5)}))
    lit = np.array(cellim)[..., 0] == 255
    assert (red[lit][:, 1] == 0).all() and (red[lit][:, 3] <= np.array(cellim)[lit][:, 3] // 2 + 1).all(), 'letter red, half'
    m = bitmap_font_files([parse_kv('BitmapFontFiles { "Big" "materials/vgui/fonts/A.vbf" }')], [tmp, tmp])
    assert m['big'] == (os.path.join(tmp, 'materials', 'vgui', 'fonts', 'A.vbf'), os.path.join(tmp, 'materials', 'vgui', 'fonts', 'a.vtf'))
    # the game's cells, measured 2026-10-12: past 0xFF from Tahoma at the font's height, 2 px of room, spaces drawn,
    # underlined smoothed letters a to the left
    ar, mar = Win32Font('Impact', 40, 400, flags=FONTFLAG['antialias'] | FONTFLAG['rotary']), Win32Font('Marlett', 40, 400)
    assert ar.other('Ж').face == 'Tahoma' and ar.other('A') is None and mar.other('Ж') is None, 'Tahoma past 0xFF'
    assert ar.cell('Ж').shape[0] == ar.height + 2 != ar.other('Ж').height + 2, 'squeezed to the font\'s height'
    sp = ar.cell(' ')
    assert sp.shape == (ar.height + 2, ar.abc(' ')[1] + 2, 4) and sp[(ar.height + 2) // 2, 0, 3] == 255, 'space: the line'
    assert [ch for _, ch in layout(ar, 'a b')[0]] == ['a', ' ', 'b'], 'spaces drawn'
    ul = Win32Font('Arial', 40, 400, flags=FONTFLAG['antialias'] | FONTFLAG['underline'])
    assert [x for x, _ in layout(ul, 'Q')[0]] == [-ul.abc('Q')[0]], 'underlined, smoothed: a to the left'
    for x in (ar, mar, ul): x.close()
    # what the code review found (2026-10-17): none of these may crash, corrupt or empty a file
    sp = os.path.join(tmp, 'safe.res')
    for bad in ('Ari"al', 'a' + chr(10) + 'b'):                 # (a quote or a line break would break the file)
        try: set_font_entry('"S" { Fonts { } }', 'A', '1', {'name': bad}); raise AssertionError(f'{bad!r} taken')
        except ValueError: pass
    try: add_bitmap_file('"S" { Fonts { } }', 'x"y', 'x.vbf'); raise AssertionError('quote taken')
    except ValueError: pass
    one = set_font_entry('"S" { Fonts { "A" { "1" { "name" "Arial" } } } }', 'A', '2', {'name': 'Tahoma'})
    assert find(find(parse_kv(one)[0][1], 'Fonts'), 'A')[1][0] == '2', 'a one-line block: the entry inside it'
    one = add_bitmap_file('"S"' + chr(10) + '{' + chr(10) + ' BitmapFontFiles { "a" "a.vbf" }' + chr(10) + ' Fonts { }' + chr(10) + '}', 'b', 'b.vbf')
    assert sorted(k for k, _ in find(parse_kv(one)[0][1], 'BitmapFontFiles')) == ['a', 'b'], 'a one-line list: the line inside it'
    Win32Font('Arial', 8, blur=12, flags=FONTFLAG['antialias']).cell('A')        # (blur wider than the cell)
    open(sp, 'w').write('#base "safe.res"\n"S" { Fonts { } }\n'); load_scheme(sp)   # (a #base back to itself)
    assert sized({'tall': '12px'}, 1080, False)[1] == 12 and sized({'tall': '-50'}, 1080, False)[1] == 0, 'numbers as the game reads them'
    parse_kv_at('"a" { "b" "c" [$WIN32]')                                          # (a condition last in the file)
    # the 2026-10-18 audit: #base merging (a byte-order mark too), list blocks the parser finds, numbers, conditions
    open(os.path.join(tmp, 'base.res'), 'w').write('"S" { Fonts { "A" { "1" { "name" "Tahoma" "tall" "9" } } "B" { "1" { "tall" "7" } } } }')
    for mark in ('', '\ufeff'):
        open(sp, 'w', encoding='utf-8').write(mark + '#base "base.res"' + chr(10) + '"S" { Fonts { "A" { "1" { "name" "Arial" } } } }')
        root, files = load_scheme(sp, read=lambda q: open(q, 'rb').read().decode('latin-1'))
        a = dict(font_entries(root, 'A'))['1']
        assert len(files) == 2 and a == {'name': 'Arial', 'tall': '9'} and font_entries(root, 'B'), (mark, a, files)
    nl = chr(10)
    two_lists = add_bitmap_file('"S"' + nl + '{' + nl + ' BitmapFontFiles // mine' + nl + ' {' + nl + '  "a" "a.vbf"' + nl + ' }' + nl + ' Fonts { }' + nl + '}', 'b', 'b.vbf')
    assert two_lists.count('BitmapFontFiles') == 1 and [k for k, _ in find(parse_kv(two_lists)[0][1], 'BitmapFontFiles')] == ['a', 'b'], 'a comment after the name'
    cf = '"S"' + nl + '{' + nl + ' CustomFontFiles' + nl + ' {' + nl + '  "1" { "font" "a.ttf" }' + nl + '  "2" "b.ttf"' + nl + ' }' + nl + ' Fonts { }' + nl + '}'
    assert add_custom_font(cf, 'b.ttf', '3') == cf, 'listed already, after a block-form entry'
    assert (atoi('700px'), atoi('true'), atoi(None, 5), atof('1.5x'), atof('')) == (700, 0, 5, 1.5, 0.0), 'atoi / atof'
    assert sized({'scalex': '2', 'scaley': '1.5x'}, 1080, False)[4:] == (2.0, 1.5), 'each scale on its own'
    assert fe(parse_kv('"S" { Fonts { "C" { "1" { "name" "Arial" [$win32] } } } }')[0][1], 'C', 1080)[0].get('name') == 'Arial', 'conditions ignore case'
    # a page without point sampling: bilinear the card's way, still the letters
    lin = os.path.join(tmp, 'lin.vtf'); v = bytearray(open(os.path.join(tmp, 'a.vtf'), 'rb').read()); v[20] &= 0xFE; open(lin, 'wb').write(bytes(v))
    bl = BitmapFont(os.path.join(tmp, 'a.vbf'), lin, 2.0, 2.0)
    assert not bl.point and bl.cell('S')[..., 3].max() == 255 and bl.cell('S').shape[0] == bl.height + 2, 'bilinear, scaled'
    assert parse_kv('"a" "dir' + chr(92) + '" "b" "c"') == [('a', 'dir' + chr(92)), ('b', 'c')], 'no escapes'
    assert block_text('"S" { Fonts { "A" { "1" { "name" "X" } } "B" { } } }', 'A')[1].startswith('"A"'), 'Raw: a one-line block'
    print('cssfont self-check passed')
