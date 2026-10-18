"""A desktop photo metadata viewer and copy editor."""
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import engine
from options import parse_extra

MODES = {'位置情報を削除':'gps', 'メタデータをまとめて削除':'clean', '項目を編集':'edit',
         '撮影時刻をずらす':'shift', '別の写真・XMPからコピー':'copy', 'XMPファイルへ書き出す':'xmp'}
FIELDS = {'撮影者':'EXIF:Artist', '著作権':'EXIF:Copyright', 'タイトル':'XMP-dc:Title',
          '説明':'XMP-dc:Description', '撮影日時':'EXIF:DateTimeOriginal'}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('きうい写真情報')
        self.geometry('1080x830')
        self.minsize(900, 720)
        self.paths = []
        self.data = []
        self.output = None
        self.busy = False
        self.closing = False
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.controls = []
        self.status = tk.StringVar(value='写真を選んで「情報を読む」を押してください。')
        self.filter = tk.StringVar()
        self.mode = tk.StringVar(value=next(iter(MODES)))
        self.appearance = tk.BooleanVar(value=True)
        self.hours = tk.StringVar(value='1')
        self.source = tk.StringVar()
        self.values = {tag: (tk.BooleanVar(), tk.StringVar()) for tag in FIELDS.values()}
        pad = ttk.Frame(self, padding=14)
        pad.pack(fill='both', expand=True)
        ttk.Label(pad, text='きうい写真情報', font=('Yu Gothic UI', 19, 'bold')).pack(anchor='w')
        ttk.Label(pad, text='写真の情報を調べて、共有前に整理。処理結果は新しいフォルダーへ保存します。').pack(anchor='w', pady=(2, 10))
        row = ttk.Frame(pad); row.pack(fill='x')
        self.button(row, '写真・ファイルを選ぶ（F4）', self.pick).pack(side='left')
        self.button(row, '選択をクリア', self.clear).pack(side='left', padx=7)
        self.button(row, '情報を読む（F5）', self.read).pack(side='left')
        self.count = ttk.Label(row, text='未選択'); self.count.pack(side='left', padx=12)
        if not (engine.ROOT/'native/exiftool_files/perl.exe').is_file():
            setup = ttk.Frame(pad); setup.pack(fill='x', pady=7)
            self.button(setup, 'ExifToolを準備（初回のみ）', self.prepare).pack(side='left')
            ttk.Label(setup, text='公式配布元から約11 MB取得します。準備後はオフラインで使えます。').pack(side='left', padx=8)
        self.files = tk.Listbox(pad, height=3, exportselection=False)
        self.files.pack(fill='x', pady=8)
        self.controls.append(self.files)
        self.tabs = ttk.Notebook(pad); self.tabs.pack(fill='both', expand=True)
        view = ttk.Frame(self.tabs, padding=9); edit = ttk.Frame(self.tabs, padding=9)
        self.tabs.add(view, text='情報を見る'); self.tabs.add(edit, text='コピーを作って整理する')
        row = ttk.Frame(view); row.pack(fill='x', pady=(0, 7))
        ttk.Label(row, text='タグ・値で絞り込み').pack(side='left')
        entry = ttk.Entry(row, textvariable=self.filter, width=35); entry.pack(side='left', padx=7)
        self.filter.trace_add('write', lambda *_: self.render())
        self.button(row, 'JSON保存', lambda: self.save('json')).pack(side='right', padx=4)
        self.button(row, 'CSV保存', lambda: self.save('csv')).pack(side='right')
        self.button(row, '選択値をコピー', self.copy_value).pack(side='right', padx=4)
        table = ttk.Frame(view); table.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(table, columns=('file','tag','value'), show='headings', selectmode='browse')
        for key, label, width in [('file','ファイル',170), ('tag','グループ・タグ',250), ('value','値',470)]:
            self.tree.heading(key, text=label); self.tree.column(key, width=width, minwidth=80)
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side='left', fill='both', expand=True); scroll.pack(side='right', fill='y')
        ttk.Label(view, text='JSON・CSVは絞り込み前の全情報です。位置情報やファイルのフルパスが含まれるため、共有前に内容を確認してください。', wraplength=900).pack(anchor='w', pady=7)
        row = ttk.Frame(edit); row.pack(fill='x')
        ttk.Label(row, text='操作').pack(side='left')
        combo = ttk.Combobox(row, textvariable=self.mode, values=list(MODES), state='readonly', width=33)
        combo.pack(side='left', padx=9); combo.bind('<<ComboboxSelected>>', lambda _: self.mode_changed())
        self.controls.append(combo)
        self.options = ttk.Frame(edit); self.options.pack(fill='both', expand=True, pady=12)
        self.panels = {}
        gps = ttk.Frame(self.options); self.panels['gps'] = gps
        ttk.Label(gps, text='EXIFのGPS、XMPのGPS・場所、IPTCの地域情報を削除したコピーを作ります。\n独自のタグや説明文に書かれた場所は残る場合があります。保存後に結果を確認してください。', wraplength=850).pack(anchor='w')
        clean = ttk.Frame(self.options); self.panels['clean'] = clean
        ttk.Label(clean, text='ExifToolで削除できるメタデータをまとめて取り除きます。\n画像の写り込みや文字は消えません。完全な匿名化を保証する機能ではありません。', wraplength=850).pack(anchor='w')
        check = ttk.Checkbutton(clean, text='向き（Orientation）と色（ICCプロファイル）を残す', variable=self.appearance)
        check.pack(anchor='w', pady=10); self.controls.append(check)
        ttk.Label(clean, text='オフにすると、写真の表示方向や色が変わる場合があります。', wraplength=850).pack(anchor='w')
        fields = ttk.Frame(self.options); self.panels['edit'] = fields
        ttk.Label(fields, text='チェックした項目だけ変更します。値が空なら、その項目を削除します。').grid(row=0, column=0, columnspan=2, sticky='w')
        for index, (label, tag) in enumerate(FIELDS.items(), 1):
            enabled, value = self.values[tag]
            control = ttk.Checkbutton(fields, text=label, variable=enabled); control.grid(row=index,column=0,sticky='w', pady=3); self.controls.append(control)
            control = ttk.Entry(fields, textvariable=value, width=66); control.grid(row=index,column=1,sticky='ew',padx=7); self.controls.append(control)
        fields.columnconfigure(1, weight=1)
        ttk.Label(fields, text='撮影日時の例：2026:10:18 12:30:00').grid(row=6,column=1,sticky='w',padx=7)
        ttk.Label(fields, text='追加タグ（1行に EXIF:Make=カメラ名 など。EXIF / IPTC / XMP、最大20行）').grid(row=7,column=0,columnspan=2,sticky='w',pady=(10,3))
        self.extra = tk.Text(fields, height=4, width=75); self.extra.grid(row=8,column=0,columnspan=2,sticky='ew'); self.controls.append(self.extra)
        shift = ttk.Frame(self.options); self.panels['shift'] = shift
        ttk.Label(shift, text='EXIFの撮影日時・作成日時・変更日時（AllDates）を指定時間ずらします。\nファイルシステムの更新日時は対象にしません。存在しないタグは作成しません。').pack(anchor='w')
        r = ttk.Frame(shift); r.pack(anchor='w', pady=12)
        control = ttk.Spinbox(r, from_=-168, to=168, textvariable=self.hours, width=8); control.pack(side='left'); self.controls.append(control)
        ttk.Label(r, text='時間（例：-9。0以外の整数、±168まで）').pack(side='left', padx=8)
        copy = ttk.Frame(self.options); self.panels['copy'] = copy
        ttk.Label(copy, text='選んだ写真やXMPにある、書き込み可能なタグをコピーします。\n選択元の位置情報も移る場合があります。撮影者名などの権利情報も確認してください。').pack(anchor='w')
        self.button(copy, 'コピー元の写真・XMPを選ぶ', self.pick_source).pack(anchor='w', pady=12)
        ttk.Label(copy, textvariable=self.source, wraplength=850).pack(anchor='w')
        xmp = ttk.Frame(self.options); self.panels['xmp'] = xmp
        ttk.Label(xmp, text='各写真からXMPに変換できる情報を取り出し、別の.xmpファイルへ保存します。\nすべての独自タグがXMPに変換できるわけではありません。').pack(anchor='w')
        self.button(edit, 'コピーを作って保存…', self.process).pack(anchor='w', pady=(6, 8))
        ttk.Label(edit, text='保存：JPEG / PNG / WebP。その他は読み取りのみ。最大100ファイル・各256 MiB・合計1 GiB・一括処理5分。', wraplength=900).pack(anchor='w')
        row = ttk.Frame(pad); row.pack(fill='x', pady=(10, 4))
        self.stop = ttk.Button(row, text='停止', command=self.cancel.set, state='disabled'); self.stop.pack(side='left')
        self.button(row, '保存先を開く', self.open_output).pack(side='left', padx=8)
        ttk.Label(pad, textvariable=self.status, wraplength=990).pack(anchor='w')
        self.mode_changed()
        self.bind('<F4>', lambda _: self.pick())
        self.bind('<F5>', lambda _: self.read())
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(80, self.poll)

    def button(self, parent, text, command):
        b = ttk.Button(parent, text=text, command=command); self.controls.append(b); return b

    def prepare(self):
        if self.busy: return
        def work():
            engine.prepare(self.cancel, lambda t:self.events.put(('progress',t)))
            return None, [], [{'file':'', 'warning':'初回準備が完了しました。写真を選んで情報を読み取れます。'}]
        self.start(work)

    def mode_changed(self):
        for panel in self.panels.values(): panel.pack_forget()
        self.panels[MODES[self.mode.get()]].pack(fill='both', expand=True)

    def pick(self):
        if self.busy: return
        files = filedialog.askopenfilenames(parent=self, filetypes=[('写真・メディア','*.jpg *.jpeg *.png *.webp *.tif *.tiff *.heic *.dng *.mp4 *.pdf *.xmp'), ('すべて','*.*')])
        if files:
            if len(files)>100: messagebox.showerror('選択できません','100ファイルまでです。',parent=self); return
            self.paths=list(files); self.files.delete(0,'end')
            for p in files: self.files.insert('end', Path(p).name)
            self.count.configure(text=f'{len(files)}ファイル'); self.data=[]; self.render()

    def clear(self):
        if self.busy: return
        self.paths=[]; self.data=[]; self.files.delete(0,'end'); self.count.configure(text='未選択'); self.render()

    def pick_source(self):
        if self.busy: return
        p=filedialog.askopenfilename(parent=self)
        if p: self.source.set(p)

    def start(self, work):
        if self.busy: return
        self.busy=True; self.cancel.clear(); self.status.set('処理中…')
        for w in self.controls: w.configure(state='disabled')
        self.stop.configure(state='normal')
        def worker():
            try: self.events.put(('done',work()))
            except Exception as exc: self.events.put(('error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def read(self):
        if self.busy: return
        paths=list(self.paths)
        self.start(lambda: (None, engine.inspect(paths,self.cancel), []))

    def process(self):
        if self.busy: return
        try:
            options={'mode':MODES[self.mode.get()], 'appearance':self.appearance.get(), 'hours':self.hours.get(), 'source':self.source.get()}
            values={tag:v.get() for tag,(on,v) in self.values.items() if on.get()}
            extra=parse_extra(self.extra.get('1.0','end-1c'))
            if {t.lower() for t in values} & {t.lower() for t in extra}: raise ValueError('同じタグを二重に指定しないでください。')
            options['values']={**values,**extra}; engine.edit_args(options)
            if not self.paths: raise ValueError('ファイルを選んでください。')
        except Exception as exc: messagebox.showerror('指定を確認してください',str(exc),parent=self); return
        dest=filedialog.askdirectory(parent=self,title='保存先の親フォルダーを選ぶ')
        if not dest: return
        paths=list(self.paths)
        def work():
            out,report=engine.process(paths,dest,options,self.cancel,lambda t:self.events.put(('progress',t)))
            return out, engine.inspect(sorted(out.iterdir()),self.cancel), report
        self.start(work)

    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='progress': self.status.set(value); continue
                self.busy=False
                for w in self.controls: w.configure(state='normal')
                for w in self.controls:
                    if isinstance(w,ttk.Combobox): w.configure(state='readonly')
                self.stop.configure(state='disabled')
                if kind=='done':
                    out,self.data,report=value
                    if out: self.output=out
                    self.render(); self.tabs.select(0)
                    warnings=[r['warning'] for r in report if r['warning']]
                    self.status.set((f'保存完了：{out}。保存したファイルの情報を表示しています。' if out else f'{len(self.data)}ファイルの情報を読み込みました。') + (' 警告あり：'+warnings[0][:220] if warnings else ''))
                else:
                    self.status.set(value)
                    if not self.closing: messagebox.showerror('処理を完了できません',value,parent=self)
        except queue.Empty: pass
        if self.closing and not self.busy: self.destroy(); return
        self.after(80,self.poll)

    def render(self):
        self.tree.delete(*self.tree.get_children())
        needle=self.filter.get().casefold()
        count=0
        for item in self.data:
            for tag,value in item.items():
                text=json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else str(value)
                if needle and needle not in (tag+' '+text).casefold(): continue
                self.tree.insert('', 'end',values=(Path(item.get('SourceFile','')).name,tag,text[:12000])); count+=1
                if count>=12000: return

    def copy_value(self):
        selected=self.tree.selection()
        if selected: self.clipboard_clear(); self.clipboard_append(self.tree.item(selected[0],'values')[2])

    def save(self, kind):
        if self.busy or not self.data: return
        name=filedialog.asksaveasfilename(parent=self,initialfile='写真情報.'+kind,defaultextension='.'+kind)
        if name:
            try:
                with open(name,'x',encoding='utf8',newline='') as f: f.write(engine.export_report(self.data,kind))
            except Exception as exc: messagebox.showerror('保存できません',str(exc),parent=self)

    def open_output(self):
        if self.output and self.output.is_dir(): os.startfile(self.output)

    def close(self):
        self.closing=True; self.cancel.set()


if __name__=='__main__': App().mainloop()
