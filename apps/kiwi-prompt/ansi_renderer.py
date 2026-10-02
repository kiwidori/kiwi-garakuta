import re
import runtime
SGR_RE=re.compile(r'\x1b\[([0-9;]*)m')
MAX_RENDER=128*1024

def render_ansi(widget, text):
    if not isinstance(text, str):
        return
    raw_bytes = text.encode('utf-8', 'replace')
    truncated = len(raw_bytes) > MAX_RENDER
    if truncated:
        text = raw_bytes[:MAX_RENDER].decode('utf-8', 'ignore') + '\n... (表示省略)'
    for tag in widget.tag_names():
        if tag.startswith('glow_'):
            try:
                widget.tag_delete(tag)
            except Exception:
                pass
    base_fg = str(widget.cget('foreground')) or '#000000'
    base_bg = str(widget.cget('background')) or '#ffffff'
    palette16 = ['#000000', '#800000', '#008000', '#808000', '#000080', '#800080', '#008080', '#c0c0c0', '#808080', '#ff0000', '#00ff00', '#ffff00', '#0000ff', '#ff00ff', '#00ffff', '#ffffff']

    def _color_256(n):
        n = max(0, min(255, int(n)))
        if n < 16:
            return palette16[n]
        if n < 232:
            levels = [0, 95, 135, 175, 215, 255]
            idx = n - 16
            r = levels[idx // 36 % 6]
            g = levels[idx % 36 // 6 % 6]
            b = levels[idx % 6]
            return f'#{r:02x}{g:02x}{b:02x}'
        v = max(0, min(255, 8 + (n - 232) * 10))
        return f'#{v:02x}{v:02x}{v:02x}'

    def _rgb_hex(r, g, b):
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))
        return f'#{r:02x}{g:02x}{b:02x}'

    def _font_tuple(attrs):
        style = 'normal'
        if attrs['bold'] and attrs['italic']:
            style = 'bold italic'
        elif attrs['bold']:
            style = 'bold'
        elif attrs['italic']:
            style = 'italic'
        return ('Consolas', 11, style)

    def _make_tag(attrs):
        key = (attrs['bold'], attrs['italic'], attrs['underline'], attrs['strike'], attrs['fg'], attrs['bg'])
        if key in tag_cache:
            return tag_cache[key]
        if len(tag_cache) >= 255:
            return 'glow_base'
        name = f'glow_{len(tag_cache)}'
        opts = {'font': _font_tuple(attrs), 'foreground': attrs['fg'] or base_fg, 'background': attrs['bg'] or base_bg}
        if attrs['underline']:
            opts['underline'] = True
        opts['overstrike'] = attrs['strike']
        widget.tag_configure(name, **opts)
        tag_cache[key] = name
        return name

    def _apply_sgr(params):
        nonlocal attrs
        i = 0
        while i < len(params):
            p = params[i] if params[i] != '' else '0'
            try:
                v = int(p)
            except ValueError:
                i += 1
                continue
            if v == 0:
                attrs = {'bold': False, 'italic': False, 'underline': False, 'strike': False, 'fg': None, 'bg': None}
            elif v == 1:
                attrs['bold'] = True
            elif v in (2, 22):
                attrs['bold'] = False
            elif v == 3:
                attrs['italic'] = True
            elif v == 23:
                attrs['italic'] = False
            elif v == 4:
                attrs['underline'] = True
            elif v == 24:
                attrs['underline'] = False
            elif v == 9:
                attrs['strike'] = True
            elif v == 29:
                attrs['strike'] = False
            elif 30 <= v <= 37:
                attrs['fg'] = palette16[v - 30]
            elif 90 <= v <= 97:
                attrs['fg'] = palette16[v - 90 + 8]
            elif v == 39:
                attrs['fg'] = None
            elif 40 <= v <= 47:
                attrs['bg'] = palette16[v - 40]
            elif 100 <= v <= 107:
                attrs['bg'] = palette16[v - 100 + 8]
            elif v == 49:
                attrs['bg'] = None
            elif v in (38, 48):
                target = 'fg' if v == 38 else 'bg'
                if i + 2 < len(params) and params[i + 1] == '5':
                    try:
                        n = int(params[i + 2])
                        attrs[target] = _color_256(n)
                        i += 2
                    except ValueError:
                        pass
                elif i + 4 < len(params) and params[i + 1] == '2':
                    try:
                        r, g, b = (int(params[i + 2]), int(params[i + 3]), int(params[i + 4]))
                        attrs[target] = _rgb_hex(r, g, b)
                        i += 4
                    except ValueError:
                        pass
            i += 1
    text = runtime.OSC_RE.sub('', text)
    sgr_re = re.compile('\\x1b\\[([0-9;]*)m')
    attrs = {'bold': False, 'italic': False, 'underline': False, 'strike': False, 'fg': None, 'bg': None}
    tag_cache = {}
    widget.tag_configure('glow_base', font=('Consolas', 11), foreground=base_fg, background=base_bg)
    try:
        widget.config(state='normal')
        widget.delete('1.0', 'end')
        pos = 0
        for m in sgr_re.finditer(text):
            if m.start() > pos:
                span = runtime._strip_ansi(text[pos:m.start()])
                tag_name = _make_tag(attrs)
                widget.insert('end', span, (tag_name,))
            _apply_sgr(m.group(1).split(';'))
            pos = m.end()
        if pos < len(text):
            span = runtime._strip_ansi(text[pos:])
            tag_name = _make_tag(attrs)
            widget.insert('end', span, (tag_name,))
    finally:
        widget.config(state='disabled')
