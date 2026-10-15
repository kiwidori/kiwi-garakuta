"""Desktop interface for local speech transcription."""
import json,math,os,queue,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
from core import run_batch,languages
from cli_args import validate_advanced,SCHEMA
from runtime import resource_path
MODES={'文字起こし':'transcribe','英語へ翻訳':'translate','言語の判別のみ':'detect'}
class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('きうい文字起こし');self.geometry('1050x850');self.minsize(950,780)
        self.paths=[];self.controls=[];self.q=queue.Queue();self.cancel=threading.Event();self.worker=None;self.closing=False;self.results=[];self.current=None;self.edits={};self.last_folder='';self.advanced={}
        names=languages();common={'ja':'日本語','en':'英語','zh':'中国語','ko':'韓国語','fr':'フランス語','de':'ドイツ語','es':'スペイン語'}
        self.language_lookup={'自動判別':'auto',**{common.get(code,name)+' ('+code+')':code for code,name in names.items()}}
        self.language_choices=['日本語 (ja)','英語 (en)','自動判別',*[n for n in self.language_lookup if n not in ('日本語 (ja)','英語 (en)','自動判別')]]
        self.destination=tk.StringVar(value=str(Path.home()/'Documents'));self.mode=tk.StringVar(value='文字起こし');self.language=tk.StringVar(value='日本語 (ja)');self.threads=tk.StringVar(value=str(min(4,os.cpu_count() or 1)))
        self.vad=tk.BooleanVar();self.diarize=tk.BooleanVar();self.offset=tk.StringVar(value='0');self.duration=tk.StringVar(value='0');self.prompt=tk.StringVar();self.custom_model=tk.StringVar();self.result_choice=tk.StringVar();self.status=tk.StringVar(value='音声を追加してください。WAV・MP3・FLAC・OGGに対応しています。')
        self.format_vars={key:tk.BooleanVar(value=key in ('txt','srt','vtt')) for key in ('txt','srt','vtt','lrc','csv','json')}
        self._build_ui();self.protocol('WM_DELETE_WINDOW',self.close);self.after(100,self.poll)
    def _button(self,parent,label,command,controlled=True,state='normal'):
        w=ttk.Button(parent,text=label,command=command,state=state)
        if controlled:self.controls.append(w)
        return w
    def _field(self,parent,label,var,choices=None,width=18):
        frame=ttk.Frame(parent);frame.pack(side='left',fill='x',expand=True,padx=5,pady=5);ttk.Label(frame,text=label).pack(anchor='w')
        w=ttk.Combobox(frame,textvariable=var,values=choices,state='readonly',width=width) if choices else ttk.Entry(frame,textvariable=var,width=width)
        w.pack(fill='x');self.controls.append(w);return w
    def _check(self,parent,label,var):
        w=ttk.Checkbutton(parent,text=label,variable=var);w.pack(side='left',padx=6,pady=6);self.controls.append(w);return w
    def _build_ui(self):
        self.geometry("1050x850")
        self.minsize(950, 780)
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="録音を、文章と字幕に。", font=("Meiryo UI", 17, "bold")).pack(anchor="w")
        ttk.Label(root, text="音声はPC内で処理します。日本語対応モデルを同梱しています。").pack(anchor="w")

        files_lf = ttk.LabelFrame(root, text="ファイル", padding=8)
        files_lf.pack(fill="x", pady=(10, 5))
        self.files = tk.Listbox(files_lf, height=4, selectmode=tk.EXTENDED)
        self.files.pack(side="left", fill="both", expand=True)
        self.controls.append(self.files)
        btn_frame = ttk.Frame(files_lf)
        btn_frame.pack(side="right", fill="y")
        self._button(btn_frame, "追加", self.add_files).pack(pady=2)
        self._button(btn_frame, "一覧から除く", self.remove_files).pack(pady=2)

        dest_row = ttk.Frame(root)
        dest_row.pack(fill="x", pady=5)
        self._field(dest_row, "出力先", self.destination, width=60)
        self._button(dest_row, "参照", self.choose_destination).pack(side="left", padx=(5, 0))

        notebook = ttk.Notebook(root)
        notebook.pack(fill="x", pady=5)
        self._notebook=notebook
        notebook.bind("<<NotebookTabChanged>>",self.fit_settings)
        self.after_idle(self.fit_settings)
        basic_tab = ttk.Frame(notebook, padding=8)
        additional_tab = ttk.Frame(notebook, padding=8)
        notebook.add(basic_tab, text="基本")
        notebook.add(additional_tab, text="詳細")

        row1 = ttk.Frame(basic_tab)
        row1.pack(fill="x", pady=2)
        self._field(row1, "操作", self.mode, choices=list(MODES))
        self._field(row1, "言語", self.language, choices=self.language_choices)
        self._field(row1, "スレッド数", self.threads)

        row2 = ttk.Frame(basic_tab)
        row2.pack(fill="x", pady=2)
        for fmt in ['txt', 'srt', 'vtt', 'lrc', 'csv', 'json']:
            self._check(row2, fmt.upper(), self.format_vars[fmt])

        row3 = ttk.Frame(additional_tab)
        row3.pack(fill="x", pady=2)
        self._field(row3, "開始位置（秒）", self.offset)
        self._field(row3, "長さ（秒、0は音声の終わり）", self.duration)

        row4 = ttk.Frame(additional_tab)
        row4.pack(fill="x", pady=2)
        self._check(row4, "無音を除く（VAD）", self.vad)
        self._check(row4, "左右チャンネルを区別", self.diarize)

        row5 = ttk.Frame(additional_tab)
        row5.pack(fill="x", pady=2)
        self._field(row5, "固有名詞など（任意）", self.prompt, width=60)

        row6 = ttk.Frame(additional_tab)
        row6.pack(fill="x", pady=2)
        self._field(row6, "互換モデル（空欄なら同梱）", self.custom_model, width=50)
        self._button(row6, "参照", self.choose_model).pack(side="left", padx=(5, 0))
        self._button(row6, "詳細編集", self.edit_details).pack(side="left", padx=5)

        ctrl_row = ttk.Frame(root)
        ctrl_row.pack(fill="x", pady=10)
        self.start_button = self._button(ctrl_row, "開始", self.start, controlled=True, state='normal')
        self.start_button.pack(side="left")
        self.stop_button = self._button(ctrl_row, "停止", self.stop, controlled=False, state='disabled')
        self.stop_button.pack(side="left", padx=5)
        self._button(ctrl_row, "ヘルプ", self.show_help).pack(side="left", padx=5)

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", pady=5)

        res_row = ttk.Frame(root)
        res_row.pack(fill="x", pady=5)
        self.result_selector = ttk.Combobox(res_row, textvariable=self.result_choice, state="readonly")
        self.result_selector.bind("<<ComboboxSelected>>", self.select_result)
        self.controls.append(self.result_selector)
        self.result_selector.pack(side="left", fill="x", expand=True)
        self.open_button = self._button(res_row, "フォルダを開く", self.open_folder, controlled=False, state='disabled')
        self.open_button.pack(side="left", padx=5)
        self.save_button = self._button(res_row, "修正版保存", self.save_edited, controlled=True, state='disabled')
        self.save_button.pack(side="left")

        preview_frame = ttk.Frame(root)
        preview_frame.pack(fill="both", expand=True, pady=5)
        try:
            from tkinter.scrolledtext import ScrolledText
            self.preview = ScrolledText(preview_frame, wrap="word", height=10, font=("Meiryo UI", 11))
        except ImportError:
            self.preview = tk.Text(preview_frame, wrap="word", height=10, font=("Meiryo UI", 11))
            sb = ttk.Scrollbar(preview_frame, command=self.preview.yview)
            self.preview.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
        self.preview.pack(fill="both", expand=True)
        self.controls.append(self.preview)

        status_label = ttk.Label(root, textvariable=self.status, wraplength=980, anchor="w")
        status_label.pack(fill="x", pady=5)
        ttk.Label(root, text="文章の修正は別名TXTへ保存できます。字幕などは認識時の内容です。認識結果は内容を確認してください。").pack(anchor="w")
    def fit_settings(self,event=None):
        if self._notebook.select():
            frame=self._notebook.nametowidget(self._notebook.select());frame.update_idletasks();self._notebook.configure(height=frame.winfo_reqheight()+8)
    def add_files(self):
        for item in filedialog.askopenfilenames(title='音声を追加',filetypes=[('音声','*.wav *.mp3 *.flac *.ogg'),('すべて','*.*')]):
            if item not in self.paths:self.paths.append(item)
        self.refresh_files()
    def remove_files(self):
        for index in reversed(self.files.curselection()):self.paths.pop(index)
        self.refresh_files()
    def refresh_files(self):
        self.files.delete(0,'end')
        for item in self.paths:self.files.insert('end',item)
    def choose_destination(self):
        item=filedialog.askdirectory(title='保存先の親フォルダー')
        if item:self.destination.set(item)
    def choose_model(self):
        item=filedialog.askopenfilename(title='互換GGMLモデル（GGUFではありません）',filetypes=[('GGMLモデル','*.bin'),('すべて','*.*')])
        if item:self.custom_model.set(item)
    def edit_details(self):
        win=tk.Toplevel(self);win.title('認識の詳細設定');win.geometry('850x650');win.transient(self);win.grab_set()
        ttk.Label(win,text='必要な項目だけJSONで指定できます。保存形式・音声・保存先・モデルの変更には画面の欄を使ってください。',wraplength=800).pack(anchor='w',padx=12,pady=10)
        ttk.Label(win,text='例: {"beam-size": 5, "max-len": 42, "split-on-word": true}',wraplength=800).pack(anchor='w',padx=12)
        box=tk.Text(win,height=10,wrap='word');box.pack(fill='both',expand=True,padx=12);box.insert('1.0',json.dumps(self.advanced,ensure_ascii=False,indent=2))
        ref=tk.Text(win,height=9,wrap='word');ref.pack(fill='both',expand=True,padx=12,pady=6)
        for key,(kind,lo,hi) in SCHEMA.items():ref.insert('end',key+': '+('true / false（有効にする場合true）' if kind=='b' else str(hi) if kind=='e' else str(lo)+' ～ '+str(hi))+'\n')
        ref.configure(state='disabled')
        def apply():
            try:value=validate_advanced(json.loads(box.get('1.0','end')))
            except (ValueError,TypeError) as e:messagebox.showerror('詳細設定',str(e),parent=win);return
            self.advanced=value;win.destroy()
        ttk.Button(win,text='適用',command=apply).pack(pady=12)
    def show_help(self):
        win=tk.Toplevel(self);win.title('きうい文字起こしの使い方');win.geometry('850x650');box=tk.Text(win,wrap='word');box.pack(fill='both',expand=True)
        text='音声を追加し、保存先・操作・言語を選んで開始します。結果は新しいフォルダーへ保存します。動画・M4A・マイクからの録音には対応していません。\n\n文章は修正して別名のTXTへ保存できます。字幕・JSONなどは認識時の内容で、文章の修正は反映されません。認識結果には誤りや、音声にない文章が含まれる場合があります。内容を確認してください。\n\n同梱モデルは日本語対応のsmall-q5_1です。英語への翻訳・言語判別もできます。VADは無音の除外に使いますが、発話が欠ける場合もあるため初期状態はオフです。左右の区別はステレオ音声が必要で、人を識別する機能ではありません。\n\n長さ0は音声の終わりまで処理します。音声は最長1時間です。VADとCPU分割（processors）では、開始位置・長さを0にしてください。1ファイル200 MiB、20件・合計1 GiBまで。処理は1件30分、各出力ファイル16 MiBまで。失敗・停止した場合、その回の結果は保存しません。既存の保存結果や元音声は変更しません。CSVの文章が数式として解釈されそうな場合、先頭にアポストロフィを付けます。\n\n互換Whisper GGMLモデルを手元のファイルから指定できます。GGUFは使えません。モデルに合う言語・DTW設定を選んでください。tinydiarizeには専用TDRZモデルが必要です。GPU・OpenVINO・マイク録音・サーバー・Unixカラオケスクリプトの生成や実行は対象外です。\n\nWindows 11 x64とMicrosoft Visual C++ v14再頒布可能パッケージ（x64）が必要です。GPUは不要です。音声はPC内だけで処理します。\n\n'
        text+=Path(resource_path('upstream-help.txt',Path(__file__).resolve().parent)).read_text(encoding='utf8');box.insert('1.0',text);box.configure(state='disabled')
    def _milliseconds(self,var):
        value=float(var.get())
        if not math.isfinite(value) or not 0<=value<=3600:raise ValueError('開始・長さは0～3600秒で入力してください。')
        return round(value*1000)
    def start(self):
        if self.worker and self.worker.is_alive():return
        try:
            formats=[key for key,value in self.format_vars.items() if value.get()]
            if not formats:raise ValueError('保存形式を1つ以上選んでください。')
            params=dict(paths=list(self.paths),destination=self.destination.get(),language=self.language_lookup[self.language.get()],mode=MODES[self.mode.get()],threads=int(self.threads.get()),vad=self.vad.get(),diarize=self.diarize.get(),offset_ms=self._milliseconds(self.offset),duration_ms=self._milliseconds(self.duration),prompt=self.prompt.get(),advanced=dict(self.advanced),custom_model=self.custom_model.get().strip(),formats=formats)
            if not self.paths:raise ValueError('音声を追加してください。')
            validate_advanced(params['advanced'])
        except (ValueError,KeyError) as e:messagebox.showerror('認識の設定',str(e));return
        self.cancel.clear();self.last_folder='';self.open_button.configure(state='disabled')
        for control in self.controls:control.configure(state='disabled')
        self.stop_button.configure(state='normal');self.progress.start(12);self.status.set('同梱モデルを準備しています…')
        def notify(index,total,name):self.q.put(('progress',f'{index+1}/{total}件を認識しています: '+name))
        def work():
            try:self.q.put(('done',run_batch(**params,cancel=self.cancel,notify=notify)))
            except Exception as e:self.q.put(('error',str(e)))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
    def poll(self):
        try:
            kind,result=self.q.get_nowait()
            if kind=='progress':self.status.set(result)
            else:
                self.progress.stop()
                for control in self.controls:control.configure(state='readonly' if isinstance(control,ttk.Combobox) else 'normal')
                self.stop_button.configure(state='disabled');self.worker=None
                if kind=='done':
                    self.results=result['items'];self.edits={};self.current=None;self.last_folder=result['folder'];self.result_selector.configure(values=[f'{i+1:02d} '+item['source'] for i,item in enumerate(self.results)])
                    self.result_selector.current(0);self.select_result();self.open_button.configure(state='normal');self.status.set('完了しました。新しいフォルダーへ保存しました。内容を確認してください。')
                else:self.status.set('停止しました。' if self.cancel.is_set() else '認識できませんでした。');messagebox.showerror('文字起こし',result) if not self.closing and not self.cancel.is_set() else None
                self.save_button.configure(state='normal' if self.results else 'disabled')
                if self.closing:self.destroy();return
        except queue.Empty:pass
        self.after(100,self.poll)
    def select_result(self,event=None):
        if self.current is not None:self.edits[self.current]=self.preview.get('1.0','end-1c')
        index=self.result_selector.current()
        if not 0<=index<len(self.results):return
        self.current=index;item=self.results[index];self.preview.delete('1.0','end');text=item['text'] or ('判別した言語: '+item['language'] if item['mode']=='detect' else '文字として認識できた発話はありません。');self.preview.insert('1.0',self.edits.get(index,text))
    def save_edited(self):
        if self.current is None:return
        body=self.preview.get('1.0','end-1c')
        if len(body.encode('utf8'))>16*1024**2:messagebox.showerror('保存','文章は16 MiBまでです。');return
        name=Path(self.results[self.current]['source']).stem+'-修正.txt'
        path=filedialog.asksaveasfilename(title='修正した文章を別名で保存',initialdir=self.last_folder,initialfile=name,defaultextension='.txt',filetypes=[('テキスト','*.txt')],confirmoverwrite=False)
        if not path:return
        try:
            with open(path,'x',encoding='utf8') as f:f.write(body)
        except FileExistsError:messagebox.showerror('保存','既存のファイルは上書きしません。別の名前を指定してください。')
        except OSError as e:messagebox.showerror('保存',str(e))
    def open_folder(self):
        if self.last_folder and Path(self.last_folder).is_dir():os.startfile(self.last_folder)
    def stop(self):self.cancel.set();self.status.set('停止しています…')
    def close(self):
        if self.worker and self.worker.is_alive():self.closing=True;self.stop()
        else:self.destroy()
if __name__=='__main__':App().mainloop()
