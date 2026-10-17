# test_fonttester.py: drives the window hidden, on a copy of the HUD, and checks it does what it says
# (python test_fonttester.py). Nothing here writes to the real HUD or the real settings.
import importlib.util, os, shutil, sys, tempfile, time, types
import customtkinter as ctk
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('ft', os.path.join(HERE, 'fonttester.pyw'))
ft = importlib.util.module_from_spec(spec); spec.loader.exec_module(ft)
C = ft.C
temp = tempfile.mkdtemp()                                  # (everything this writes; removed at the end)
ft.SETTINGS = os.path.join(temp, 'settings.json')

# the HUD: a copy of tests/hud (fonts every Windows PC has), its CenterPrintText named Lexend with a drop shadow
hud = os.path.join(temp, 'huds', 'hud')
shutil.copytree(os.path.join(HERE, 'tests', 'hud', 'resource'), os.path.join(hud, 'resource'))
scheme = os.path.join(hud, 'resource', 'ClientScheme.res')
C.edit_scheme(scheme, lambda t: C.set_font_entry(t, 'CenterPrintText', '1', {'name': 'Lexend', 'tall': '18', 'weight': '700', 'additive': '0',
                                                                          'outline': '0', 'antialias': '1', 'dropshadow': '1'}))
ft.CUSTOM = os.path.dirname(hud)

ctk.set_appearance_mode('dark')
root = ctk.CTk(); root.withdraw()
app = ft.App(root)
def pump(s=0.3):
    end = time.time() + s
    while time.time() < end: root.update(); time.sleep(0.005)
def pick(iid):
    app.tree.selection_set([iid]); app.tree.focus(iid); pump()
pump()
assert app.tree.selection() == () and app.active is None, 'the first time: nothing picked'
app.tree.selection_set(['Client: CenterPrintText', 'Source: Trebuchet24']); app.tree.focus('Source: Trebuchet24'); pump()
assert app.scene is not None and app.scene.shape == (1440, 2560, 3)

# the right side: an option changed reaches the font; changed back, nothing kept
pick('Source: Trebuchet24')
S = lambda: app.state('Source: Trebuchet24')
base_h = app.font('Source: Trebuchet24')[0].height
start_tall, undo_n = S()['tall'], len(app.undo)
app.values['tall'].set(str(int(start_tall) + 12)); pump(0.6)             # (in the scheme by itself, a moment later)
assert app.font('Source: Trebuchet24')[0].height > base_h and len(app.undo) == undo_n + 1, 'in the scheme by itself'
assert app.save_button.cget('text').startswith('Save  '), 'not saved yet'
app.undo_last(); pump()
assert S()['tall'] == start_tall and len(app.undo) == undo_n, 'undone'
# − / +: weight in 100s, tall in 1s
w0, t0 = int(app.values['weight'].get()), int(app.values['tall'].get())
app.value_widgets['weight'].plus.invoke(); app.value_widgets['tall'].minus.invoke(); pump()
assert S()['weight'] == str(w0 + 100) and S()['tall'] == str(t0 - 1)
app.value_widgets['weight'].minus.invoke(); app.value_widgets['tall'].plus.invoke(); pump()
# a tick puts the line in the block, unticked takes it out; a value at the game's default (blur 0) takes it out too
app.flags['italic'].set(True); app.flagged('italic'); pump()
assert S()['italic'] == '1' and app.key_labels['italic'].cget('text_color') == ft.TEXT
app.flags['italic'].set(False); app.flagged('italic'); pump()
assert S()['italic'] is None and app.key_labels['italic'].cget('text_color') == ft.MUTED, 'unticked: out of the block'
app.values['blur'].set('2'); pump(); assert S()['blur'] == '2'
app.values['blur'].set('0'); pump(); assert S()['blur'] is None, 'the default: out of the block'
app.flush(); pump()
# the rows (sorted when a font is picked, not while it's edited): the block's options first, in its order, then a
# line, then the rest; moving one changes the written order
pick('Client: HudHintText'); pick('Source: Trebuchet24')
o = S(); have = app.present(o)
rows = sorted(app.rows, key=lambda k: app.rows[k].grid_info()['row'])
assert rows[:len(have)] == have and app.divider.grid_info() and all(o[k] is None for k in rows[len(have):])
app.move_key(have[-1], 0); pump()
assert app.present(S())[0] == have[-1] and list(app.target('Source: Trebuchet24')[3])[0] == have[-1], 'written first'
app.move_key(have[-1], len(have)); pump()
assert app.present(S()) == have
app.flush(); pump()

# a change to a font with an entry per screen: a new one from just above the last range below to 9999, before the
# one used now; Undo, Save, Restore
pick('Client: HudHintText')
before = [k for k, _ in app.entries('Client: HudHintText')]
expect = C.place(app.entries('Client: HudHintText'), 1440)
h_now = app.font('Client: HudHintText')[0].height
new_tall = str(int(app.state('Client: HudHintText')['tall']) + 10)
app.values['tall'].set(new_tall); pump(); app.flush(); pump()
entries = app.entries('Client: HudHintText')
keys = [k for k, _ in entries]
key, yres, nxt = expect
assert key in keys and (nxt is None or keys.index(key) < keys.index(nxt)), (keys, expect)
assert dict(entries)[key]['yres'] == yres and yres.endswith(' 9999') and dict(entries)[key]['tall'] == new_tall
lo = int(yres.split()[0])
assert all(C.yres_range(d)[1] < lo for k, d in entries[:keys.index(key)] if C.yres_range(d)), 'starts just above the ranges before it'
assert app.font('Client: HudHintText')[0].height > h_now and app.save_button.cget('text').startswith('Save  ')
assert open(scheme, 'rb').read().decode('latin-1') == app.disk[scheme], 'not on disk until Save'
app.undo_last(); pump()
assert [k for k, _ in app.entries('Client: HudHintText')] == before, 'undone'
app.values['tall'].set(new_tall); pump(); app.flush(); pump()
app.save(); pump()
assert f'"{key}"' in open(scheme, encoding='latin-1').read() and app.save_button.cget('text') == 'Save'
app.restore(); pump()
assert key not in [k for k, _ in app.entries('Client: HudHintText')]
app.save(); pump()
assert f'"{key}"' not in open(scheme, encoding='latin-1').read(), 'restored and saved'

# Raw: the right side is the block as the file has it, from its name to the line before the next font's
app.raw.set(True); app.toggle_raw(); pump()
shown = app.raw_box.get('1.0', 'end-1c')
line, block = C.block_text(app.texts[scheme], 'HudHintText')
assert shown.startswith('HudHintText') and app.side_view.get() == 'Raw', 'from the left edge'
assert [r.strip() for r in shown.split(chr(10))] == [r.strip() for r in block.split(chr(10))], 'the block, line for line'
assert app.raw_box.winfo_manager() == 'grid' and app.save_button.winfo_manager() == 'grid', 'over the name to the buttons only'
nxt = app.texts[scheme][app.texts[scheme].index(block) + len(block):].lstrip().split()[0]
assert nxt not in ('{', '}', '"1"'), nxt
app.raw.set(False); app.toggle_raw(); pump()
assert not app.raw_box.winfo_manager()
# CenterPrintText grows with the screen: changed in place, no yres, no more entries
pick('Client: CenterPrintText')
cpt = app.font('Client: CenterPrintText')[0].height
assert app.target('Client: CenterPrintText')[:2] == ('1', None) and 'grows' in app.yres_label.cget('text')
assert app.note('antialias') == ft.GROWN_NOTES['antialias'] and app.note('italic') == ft.NOTES['italic'], 'grown notes'
t = int(app.values['tall'].get()); assert f'{t} is {min(255, int(app.h() / 480 * t))} px' in app.note('tall')
app.values['weight'].set('400'); pump(); app.flush(); pump()
es = app.entries('Client: CenterPrintText')
assert len(es) == 1 and 'yres' not in es[0][1] and es[0][1]['weight'] == '400' and es[0][1]['additive'] == '0'
app.values['tall'].set('0'); pump(); app.flush(); pump()               # (the game's default: out of the block)
assert app.entries('Client: CenterPrintText')[0][1].get('tall') is None, 'tall 0: no line, not written as 0'
app.undo_last(); pump()

# Add font to HUD: the face's file in resource/fonts, listed in CustomFontFiles; Undo takes both away
pick('Source: Trebuchet24')
assert app.note('antialias') == ft.NOTES['antialias'], 'a fixed font: the plain notes'
app.values['name'].set('Arial')
app.values['weight'].set('700'); pump()
app.add_font_to_hud(); pump()
f = os.path.join(hud, 'resource', 'fonts', 'Arial-700.ttf')
assert os.path.isfile(f) and any(v == 'resource/fonts/Arial-700.ttf' for _, v in C.find(app.schemes['Client'], 'CustomFontFiles'))
app.undo_last(); pump()
assert not os.path.isfile(f) and not any('Arial' in v for _, v in C.find(app.schemes['Client'], 'CustomFontFiles'))

# Create bitmap font: grown effects, colours, a box; then the font is that bitmap font here, drawn at its size
pick('Client: CenterPrintText')
m = ft.Maker(app, show=False); pump(0.5)
m.v['outline'].set('3'); m.v['drop'].set('2'); m.v['boxed'].set(True); m.v['pad'].set('5'); m.v['letter_a'].set('80'); pump(0.5)
font, smooth, box, style = m.settings()
assert font.outline == 3 and font.drop == 2 and box == 5 and style['letter'][3] == 0.8
assert m.name.get().endswith('_o3_box') and '_s2' in m.name.get(), m.name.get()
m.name.set('tst'); m.make(); pump()
o = app.state('Client: CenterPrintText')
bf = app.font('Client: CenterPrintText')[0]
assert o['bitmap'] == '1' and o['name'] == 'tst' and isinstance(bf, C.BitmapFont)
assert app.present(o)[-1] == 'bitmap', 'Bitmap listed last (ticking it never moves it)'
assert bf.height == font.height + 10 and app.target('Client: CenterPrintText')[1] == '1 9999', 'a bitmap one: not grown'
assert any(n == 'tst' for n, _ in C.find(app.schemes['Client'], 'BitmapFontFiles'))
app.flags['bitmap'].set(False); app.flagged('bitmap'); pump()
assert isinstance(app.font('Client: CenterPrintText')[0], C.Win32Font) and app.state('Client: CenterPrintText')['name'] == 'Lexend'
for _ in range(4):                                                      # (back to before Make, one change at a time)
    if not os.path.isfile(os.path.join(hud, 'materials', 'vgui', 'fonts', 'tst.vbf')): break
    app.undo_last(); pump()
assert not os.path.isfile(os.path.join(hud, 'materials', 'vgui', 'fonts', 'tst.vbf')), 'undone: the files gone too'
assert 'tst' not in app.bitmap_names(), 'undone: not offered'

# the modes: the speedometer and jhud change on their own; real to game: CenterPrintText drawn once per send held
app.mode.set('Speedometer'); app.every.set('50'); app.restart(); pump(0.6)
speeds = set()
for _ in range(10): speeds.add(app.speed); pump(0.06)
assert len(speeds) > 3, speeds
app.draw_kind.set('Real to game'); app.restart(); pump(0.5)
assert app.copies('Client: CenterPrintText') in (3, 4, 5) and app.copies('Source: Trebuchet24') == 1, 'held 0.2 s, sent every 50 ms'
app.every.set('1'); app.restart(); pump(0.1)
drawn = app.scene; pump(0.3)
assert app.scene is not drawn, 'sent every 1 ms: still drawn'
app.mode.set('jhud'); app.every.set('700'); app.restart(); pump(0.2)
t0 = app.jtext; assert app.copies('Client: CenterPrintText') == 1
end = time.time() + 1.5
while app.jtext == t0 and time.time() < end: pump(0.01)
assert app.jtext != t0 and app.copies('Client: CenterPrintText') == 2, 'the next jump: both held (1 s)'
pump(0.45); assert app.copies('Client: CenterPrintText') == 1, 'the first one run out'
app.mode.set('Custom'); app.draw_kind.set('Draw once'); app.restart(); pump()
assert app.copies('Client: CenterPrintText') == 1

# data safety (the 2026-10-17 code review): a name Latin-1 hasn't, a clash with a change on disk, Make over a font
pick('Source: Trebuchet24')
src = os.path.join(hud, 'resource', 'SourceScheme.res'); before_bytes = open(src, 'rb').read()
app.values['name'].set('微软雅黑'); pump(); app.flush(); pump()
assert app.save() is False and open(src, 'rb').read() == before_bytes, 'not saved, the file as it was'
app.undo_last(); pump()
app.values['weight'].set('600'); pump(); app.flush(); pump()             # (an edit not saved, then the file changes outside)
open(src, 'ab').write(b'// changed outside' + chr(10).encode()); pump(1.2)
ft.messagebox.askyesno = lambda *a, **k: False
assert app.save() is False and open(src, 'rb').read().endswith(b'// changed outside' + chr(10).encode()), 'asked, not written over'
ft.messagebox.askyesno = lambda *a, **k: True
assert app.save() is True and b'600' in open(src, 'rb').read(), 'written once said yes'
pick('Client: CenterPrintText')
mk = ft.Maker(app, show=False); pump(0.3)
taken = os.path.join(hud, 'materials', 'vgui', 'fonts', 'theirs')
os.makedirs(os.path.dirname(taken), exist_ok=True); open(taken + '.vbf', 'wb').write(b'theirs')
mk.name.set('theirs'); mk.make(); pump()
assert open(taken + '.vbf', 'rb').read() == b'theirs' and 'already' in mk.msg.cget('text'), 'Make never writes over a font'
mk.close()

# a dropdown opens under (or above) its button, not in the screen's corner; see-through here, nothing shows on screen
real_top = ft.tk.Toplevel
class Clear(real_top):
    def __init__(self, *a, **k): super().__init__(*a, **k); self.attributes('-alpha', 0.0)
ft.tk.Toplevel = Clear
def walk(w):
    yield w
    for c in w.winfo_children(): yield from walk(c)
back = next(w for w in walk(root) if isinstance(w, ft.Choice) and w.get() in ft.BACKS)
back._open_dropdown_menu(); pump(0.2)
d = ft.Dropdown.now; ft.tk.Toplevel = real_top
at, bx, by = (d.top.winfo_rootx(), d.top.winfo_rooty()), back.winfo_rootx(), back.winfo_rooty()
assert at[0] == bx and at[1] in (by + back.winfo_height() + 4, by - d.top.winfo_height() - 4), (at, bx, by)
d.close()

# zoom about the pointer, drag
cw, ch = app.canvas.winfo_width(), app.canvas.winfo_height()
at = lambda x, y: (app.centre[0] + (x - cw / 2) / app.zoom, app.centre[1] + (y - ch / 2) / app.zoom)
p = at(100, 80)
for _ in range(3): app.wheel(types.SimpleNamespace(delta=120, x=100, y=80))
assert app.zoom == 3 and all(abs(a - b) < 1e-6 for a, b in zip(at(100, 80), p))
c = list(app.centre); app.grab_view(types.SimpleNamespace(x=50, y=50)); app.move_view(types.SimpleNamespace(x=80, y=50))
assert abs(app.centre[0] - (c[0] - 10)) < 1e-6
app.reset_view(); pump()
assert app.zoom == 1

# a map texture behind the text
if os.path.isfile(ft.PAK):
    app.back.set('Dust: sand wall'); app.render()
    assert len({tuple(app.scene[5, x]) for x in range(0, 300, 7)}) > 5
    app.back.set('Dark grey'); app.render()

# favourites: to the top, kept; out again
app.favourite('Client: HudHintText')
assert app.tree.get_children('')[0] == '★' and app.tree.parent('Client: HudHintText') == '★'
assert ft.load_settings()['favourites'] == ['Client: HudHintText']
app.favourite('Client: HudHintText')
assert not app.tree.exists('★')
# the next time: the HUD and the fonts picked last
app.tree.selection_set(['Client: HudHintText', 'Source: Trebuchet24']); app.tree.focus('Client: HudHintText'); pump()
root2 = ctk.CTk(); root2.withdraw()
again = ft.App(root2)
assert again.hud == app.hud and set(again.tree.selection()) == {'Client: HudHintText', 'Source: Trebuchet24'} and again.active == 'Client: HudHintText'
root2.destroy()
root.destroy()
shutil.rmtree(temp, ignore_errors=True)
print('font tester test passed')
