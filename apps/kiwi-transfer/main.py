"""File transfer interface for Windows."""
import copy,json,os,queue,sys,threading,tkinter as tk
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
from core import transfer,new_code,valid_code,validate_options,normalize_network
from runtime import resource_path
class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('きういファイル便');self.geometry('960x780');self.minsize(900,730)
        self.paths=[];self.controls=[];self.q=queue.Queue();self.cancel=threading.Event();self.worker=None;self.closing=False;self.received='';self.options={}
        self.relay_password=tk.StringVar()
        self.mode=tk.StringVar(value='send');self.code=tk.StringVar(value=new_code());self.destination=tk.StringVar(value=str(Path.home()/'Downloads'));self.lan=tk.BooleanVar(value=True);self.zip=tk.BooleanVar();self.status=tk.StringVar(value='同じLAN内のPCへ送れます。ファイルを選び、共有コードを相手に伝えてください。')
        self._build_ui();self.protocol('WM_DELETE_WINDOW',self.close);self.after(100,self.poll)
    def _build_ui(self):
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        import json, os, shutil

        self.title("きういファイル便")
        self.geometry("1000x800")
        self.minsize(920, 760)

        self.controls = []

        ttk.Label(self,text='写真・書類を、同じネットワークのPCへ。',font=('Meiryo UI',17,'bold'),padding=12).pack(anchor='w')
        main_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        main_pane.pack(fill="both", expand=True, padx=5, pady=5)

        left_frame = ttk.Frame(main_pane)
        right_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=3)
        left_frame.configure(padding=10);right_frame.configure(padding=10)
        main_pane.add(right_frame, weight=2)


        mode_frame = ttk.LabelFrame(left_frame, text="モード")
        mode_frame.pack(fill="x", pady=(0, 5))

        rb_send = ttk.Radiobutton(mode_frame, text="送信 (Send)", variable=self.mode, value="send")
        rb_recv = ttk.Radiobutton(mode_frame, text="受信 (Receive)", variable=self.mode, value="receive")
        rb_send.pack(side="left", padx=5)
        rb_recv.pack(side="left", padx=5)
        self.controls.extend([rb_send, rb_recv])

        code_frame = ttk.LabelFrame(left_frame, text="共有コード（相手だけに伝えてください）")
        code_frame.pack(fill="x", pady=(0, 5))

        entry_code = ttk.Entry(code_frame, textvariable=self.code, font=("Consolas", 12))
        entry_code.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        btn_new = ttk.Button(code_frame, text="新規生成", command=self.generate_code)
        btn_copy = ttk.Button(code_frame, text="コピー", command=self.copy_code)
        btn_new.pack(side="right", padx=2)
        btn_copy.pack(side="right", padx=2)

        self.controls.extend([entry_code, btn_new, btn_copy])

        file_frame = ttk.LabelFrame(left_frame, text="送信するファイル・フォルダー")
        file_frame.pack(fill="both", expand=True, pady=(0, 5))

        self.files = tk.Listbox(file_frame, height=7, selectmode=tk.EXTENDED)
        self.files.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        btn_add_files = ttk.Button(file_frame, text="ファイル追加", command=self.add_files)
        btn_add_folder = ttk.Button(file_frame, text="フォルダ追加", command=self.add_folder)
        btn_remove = ttk.Button(file_frame, text="一覧から除く", command=self.remove_files)

        btn_add_files.pack(side="right", padx=2, pady=(5, 0))
        btn_add_folder.pack(side="right", padx=2, pady=(5, 0))
        btn_remove.pack(side="right", padx=2, pady=(5, 0))

        self.controls.extend([self.files, btn_add_files, btn_add_folder, btn_remove])

        dest_frame = ttk.LabelFrame(left_frame, text="受信先フォルダ")
        dest_frame.pack(fill="x", pady=(0, 5))

        entry_dest = ttk.Entry(dest_frame, textvariable=self.destination)
        entry_dest.pack(side="left", fill="x", expand=True, padx=5, pady=5)

        btn_choose_dest = ttk.Button(dest_frame, text="選択...", command=self.choose_destination)
        btn_choose_dest.pack(side="right", padx=2)

        self.controls.extend([entry_dest, btn_choose_dest])

        memo_frame = ttk.LabelFrame(left_frame, text="メモ (テキスト送信)")
        memo_frame.pack(fill="x", pady=(0, 5))
        self.note = tk.Text(memo_frame, height=3, wrap="word")
        self.note.pack(fill="x", padx=5, pady=5)
        self.controls.append(self.note)

        opt_frame = ttk.Frame(left_frame)
        opt_frame.pack(fill="x", pady=(0, 5))

        chk_lan = ttk.Checkbutton(opt_frame, text="LAN内だけ（通常はこちら）", variable=self.lan)
        chk_zip = ttk.Checkbutton(opt_frame, text="フォルダをZIP圧縮", variable=self.zip)
        chk_lan.pack(side="left")
        chk_zip.pack(side="left", padx=10)

        self.controls.extend([chk_lan, chk_zip])

        relay_row = ttk.Frame(left_frame);relay_row.pack(fill="x", pady=6)
        ttk.Label(relay_row, text="独自リレーのパスワード（通常は空欄）").pack(anchor="w")
        entry_password = ttk.Entry(relay_row, textvariable=self.relay_password, show="•");entry_password.pack(fill="x")
        self.controls.append(entry_password)

        details_frame = ttk.Frame(left_frame)
        details_frame.pack(fill="x", pady=(0, 5))

        btn_details = ttk.Button(details_frame, text="詳細 (JSON)", command=self.edit_details)
        btn_help = ttk.Button(details_frame, text="ヘルプ", command=self.show_help)
        btn_details.pack(side="left")
        btn_help.pack(side="left", padx=5)

        self.controls.append(btn_details)

        action_frame = ttk.Frame(left_frame)
        action_frame.pack(fill="x", pady=(0, 5))

        self.start_button = ttk.Button(action_frame, text="送信・受信を開始", command=self.start)
        self.stop_button = ttk.Button(action_frame, text="停止", command=self.stop, state="disabled")

        self.start_button.pack(side="left", expand=True, fill="x", padx=5)
        self.stop_button.pack(side="right", expand=True, fill="x", padx=5)

        self.controls.append(self.start_button)

        self.progress = ttk.Progressbar(left_frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 5))

        open_frame = ttk.Frame(left_frame)
        open_frame.pack(fill="x")

        self.open_button = ttk.Button(open_frame, text="受信フォルダを開く", command=self.open_received, state="disabled")
        self.open_button.pack(side="left", expand=True, fill="x", padx=5)


        status_label = ttk.Label(right_frame, textvariable=self.status, font=("Meiryo UI", 10), wraplength=330)
        status_label.pack(fill="x", pady=(0, 5))

        log_label = ttk.Label(right_frame, text="ログ (最大4MiB)")
        log_label.pack(anchor="w")

        self.log = tk.Text(right_frame, height=8, width=34, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

        footer_text = ("送信側と受信側を同時に起動してください。共有コードは相手だけに伝えてください。\n"
                       "転送は暗号化されます。受信したファイルは自動では開きません。標準公開リレーはこの版では使えません。")
        footer_label = ttk.Label(self, text=footer_text, wraplength=900, justify="center", foreground="gray")
        footer_label.pack(fill="x", side="bottom", pady=(5, 0))

    def add_files(self):
        for item in filedialog.askopenfilenames(title='送るファイルを選択'):
            if item not in self.paths:self.paths.append(item)
        self.refresh_files()
    def add_folder(self):
        item=filedialog.askdirectory(title='送るフォルダーを選択')
        if item and item not in self.paths:self.paths.append(item)
        self.refresh_files()
    def remove_files(self):
        for index in reversed(self.files.curselection()):self.paths.pop(index)
        self.refresh_files()
    def refresh_files(self):
        self.files.delete(0,tk.END)
        for item in self.paths:self.files.insert(tk.END,item)
    def choose_destination(self):
        item=filedialog.askdirectory(title='受信先の親フォルダーを選択')
        if item:self.destination.set(item)
    def generate_code(self):self.code.set(new_code())
    def copy_code(self):
        try:code=valid_code(self.code.get())
        except ValueError as e:messagebox.showerror('共有コード',str(e));return
        self.clipboard_clear();self.clipboard_append(code);self.status.set('共有コードをコピーしました。相手だけに伝えてください。')
    def edit_details(self):
        win=tk.Toplevel(self);win.title('転送の詳細設定');win.geometry('790x610');win.transient(self);win.grab_set()
        ttk.Label(win,text='globalは送受信共通、sendは送信だけに適用します。設定は保存されません。',wraplength=740).pack(anchor='w',padx=14,pady=10)
        ttk.Label(win,text='例: {"global":{"throttleUpload":"500k"},"send":{"exclude":".tmp","hash":"imohash"}}',wraplength=740).pack(anchor='w',padx=14)
        from core import GLOBAL,SEND,ENUMS
        ttk.Label(win,text='global: '+', '.join(GLOBAL)+'\nsend: '+', '.join(SEND)+'\n'+str(ENUMS),wraplength=750).pack(anchor='w',padx=14,pady=8)
        box=tk.Text(win,height=14,wrap='word');box.pack(fill='both',expand=True,padx=14);box.insert('1.0',json.dumps(self.options,ensure_ascii=False,indent=2))
        def apply():
            try:value=validate_options(json.loads(box.get('1.0','end')))
            except (ValueError,TypeError) as e:messagebox.showerror('設定',str(e),parent=win);return
            self.options=value;win.destroy()
        ttk.Button(win,text='適用',command=apply).pack(pady=12)
    def show_help(self):
        win=tk.Toplevel(self);win.title('使い方とcrocのヘルプ');win.geometry('850x630')
        box=tk.Text(win,wrap='word');box.pack(fill='both',expand=True)
        text='送信側と受信側を同時に起動し、同じ共有コードを入力します。相手もこのソフト、または互換版のcrocを使ってください。\n\n受信だけをする場合は、受信を選び、相手から届いた共有コードを入力して開始します。専用の新しいフォルダーに保存します。途中停止や失敗時は受信中フォルダーが残ります。受信したファイルは信頼できる相手のものだけ開いてください。\n\nLAN内だけにチェックすると外部リレーを使いません。LANのファイアウォールやネットワーク構成により接続できない場合があります。この版の標準設定はLAN内の暗号化転送です。標準公開リレーには対応していません。LAN内だけを外す場合は独自リレーの接続先を詳細設定で指定してください。共有コードを知る人が受信できるため、公開しないでください。\n\nフォルダーを圧縮して送る場合、相手側で自動展開されます。メモはメモ.txtとして送ります。受信ファイルは自動では開きません。1時間または表示データ4 MiBを超えると停止します。転送終了まで画面の進捗は待機表示です。\n\n遠隔端末、保存型転送、リレーサーバー起動、自動更新はこの画面では行えません。部分ファイルを再開する上書き操作にも対応しません。\n\n'
        text+=Path(resource_path('upstream-help.txt',Path(__file__).resolve().parent)).read_text(encoding='utf8')
        box.insert('1.0',text);box.configure(state='disabled')
    def start(self):
        if self.worker and self.worker.is_alive():return
        try:
            code=valid_code(self.code.get());mode=self.mode.get();opts=copy.deepcopy(self.options);opts.setdefault('global',{})['local']=self.lan.get();opts.setdefault('send',{})['zip']=self.zip.get();opts=normalize_network(validate_options(opts))
            paths=list(self.paths);note=self.note.get('1.0','end-1c') if mode=='send' else ''
            if mode=='send' and paths and note:raise ValueError('ファイル送信とメモ送信は分けて実行してください。')
            if mode=='send' and not(paths or note):raise ValueError('ファイル・フォルダーを追加するか、メモを入力してください。')
            destination=self.destination.get();relay_password=self.relay_password.get()
            if mode=='receive' and not Path(destination).is_dir():raise ValueError('受信先フォルダーを選んでください。')
        except ValueError as e:messagebox.showerror('転送の設定',str(e));return
        self.cancel.clear();self.received='';self.open_button.configure(state='disabled')
        for control in self.controls:control.configure(state='disabled')
        self.stop_button.configure(state='normal');self.progress.start(12);self.status.set('送信待ち・転送中です。相手が同じコードで受信を開始してください。' if mode=='send' else '受信待ち・転送中です。完了までお待ちください。')
        self.log.configure(state='normal');self.log.delete('1.0','end');self.log.configure(state='disabled')
        def work():
            try:self.q.put(('done',transfer(mode,paths,code,destination,opts,self.cancel,note,relay_password)))
            except Exception as e:self.q.put(('error',str(e)))
        self.worker=threading.Thread(target=work,daemon=True);self.worker.start()
    def poll(self):
        try:
            kind,result=self.q.get_nowait();self.progress.stop()
            for control in self.controls:control.configure(state='normal')
            self.stop_button.configure(state='disabled');self.status.set('転送が完了しました。' if kind=='done' else '転送を完了できませんでした。')
            if kind=='done':self.received=result['folder'];text=result['log'];self.open_button.configure(state='normal' if self.received else 'disabled')
            else:text=result
            self.log.configure(state='normal');self.log.insert('1.0',text);self.log.configure(state='disabled')
            self.worker=None
            if self.closing:self.destroy();return
        except queue.Empty:pass
        self.after(100,self.poll)
    def stop(self):self.cancel.set();self.status.set('停止しています…')
    def open_received(self):
        if self.received and Path(self.received).is_dir():os.startfile(self.received)
    def close(self):
        if self.worker and self.worker.is_alive():self.closing=True;self.stop()
        else:self.destroy()
if __name__=='__main__':App().mainloop()
