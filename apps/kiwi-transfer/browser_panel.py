"""Browser delivery using the parent window's selection and receive destination."""
from pathlib import Path
import queue
import socket
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from browser_engine import native_exe
from browser_session import Session, bind_address
from prepare_send import prepare


def addresses():
    values = []
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM):
            try:
                ip = bind_address(item[4][0])
                if ip not in values and not ip.startswith('127.'):
                    values.append(ip)
            except ValueError:
                pass
    except OSError:
        pass
    return values + ['127.0.0.1']


class BrowserDialog(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title('スマホのブラウザーと受け渡す')
        self.geometry('820x820')
        self.minsize(760, 750)
        self.transient(owner)
        self.grab_set()
        self.worker = None
        self.session = None
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.closing = False
        self.folder = ''
        self.matrix = None
        self.controls = []
        ips = addresses()
        self.address = tk.StringVar(self, value=ips[0])
        self.mode = tk.StringVar(self, value=owner.mode.get())
        self.port = tk.StringVar(self, value='0')
        self.minutes = tk.StringVar(self, value='5')
        self.keep = tk.BooleanVar(self, value=False)
        self.inverted = tk.BooleanVar(self, value=False)
        self.secure = tk.BooleanVar(self, value=False)
        self.hostname = tk.StringVar(self)
        self.certificate = tk.StringVar(self)
        self.private_key = tk.StringVar(self)
        self.url = tk.StringVar(self)
        self.status = tk.StringVar(self, value='同じWi-FiのスマホでQRを読み取ります。相手側のアプリは不要です。')
        body = ttk.Frame(self, padding=15)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='写真や書類を、スマホのブラウザーへ', font=('Meiryo UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(body, text='標準のHTTPは暗号化されません。信頼できるネットワークで使い、終わったら停止してください。HTTPSは詳細設定で指定できます。',
                  wraplength=760).pack(anchor='w', pady=(8, 10))
        row = ttk.Frame(body)
        row.pack(fill='x')
        for text, value in [('このPCから送る', 'send'), ('このPCへ受け取る', 'receive')]:
            item = ttk.Radiobutton(row, text=text, variable=self.mode, value=value)
            item.pack(side='left', padx=(0, 15))
            self.controls.append(item)
        names = '、'.join(Path(p).name for p in owner.paths[:8])
        if len(owner.paths) > 8:
            names += f' ほか{len(owner.paths)-8}件'
        if not names:
            names = 'メモを送信' if owner.note.get('1.0', 'end-1c') else 'ファイル未選択（親画面で追加してください）'
        ttk.Label(body, text='親画面の選択: ' + names, wraplength=750).pack(anchor='w', pady=8)
        ttk.Label(body, text='受信先: ' + owner.destination.get(), wraplength=750).pack(anchor='w')
        network = ttk.Frame(body)
        network.pack(fill='x', pady=10)
        ttk.Label(network, text='このPCのWi-Fi / LANのIPv4').grid(row=0, column=0, sticky='w')
        address = ttk.Combobox(network, textvariable=self.address, values=ips, width=24)
        address.grid(row=1, column=0, sticky='w', padx=(0, 12))
        ttk.Label(network, text='ポート（0は自動）').grid(row=0, column=1, sticky='w')
        port = ttk.Entry(network, textvariable=self.port, width=9)
        port.grid(row=1, column=1, sticky='w', padx=(0, 12))
        ttk.Label(network, text='共有時間（分）').grid(row=0, column=2, sticky='w')
        duration = ttk.Spinbox(network, textvariable=self.minutes, from_=1, to=60, width=6)
        duration.grid(row=1, column=2, sticky='w')
        self.controls += [address, port, duration]
        details = ttk.Button(network, text='HTTPS・ホスト名…', command=self.details)
        details.grid(row=1, column=3, padx=(12, 0))
        self.controls.append(details)
        options = ttk.Frame(body)
        options.pack(fill='x')
        keep = ttk.Checkbutton(options, text='転送後も共有を続ける（最大で指定時間まで）', variable=self.keep)
        keep.pack(side='left')
        self.controls.append(keep)
        ttk.Checkbutton(options, text='QRの白黒を反転', variable=self.inverted, command=self.draw_qr).pack(side='right')
        buttons = ttk.Frame(body)
        buttons.pack(fill='x', pady=10)
        self.start_button = ttk.Button(buttons, text='共有を開始', command=self.start)
        self.start_button.pack(side='left', fill='x', expand=True)
        self.controls.append(self.start_button)
        self.stop_button = ttk.Button(buttons, text='共有を停止', command=self.stop, state='disabled')
        self.stop_button.pack(side='left', fill='x', expand=True, padx=(10, 0))
        self.canvas = tk.Canvas(body, width=300, height=300, background='white', highlightthickness=1, highlightbackground='#ddd')
        self.canvas.pack()
        ttk.Entry(body, textvariable=self.url, state='readonly').pack(fill='x', pady=(8, 4))
        self.copy_button = ttk.Button(body, text='URLをコピー', command=self.copy_url, state='disabled')
        self.copy_button.pack()
        ttk.Label(body, textvariable=self.status, wraplength=750).pack(anchor='w', pady=10)
        self.return_button = ttk.Button(body, text='受け取ったファイルを親の送信一覧へ追加', command=self.return_files, state='disabled')
        self.return_button.pack(fill='x')
        ttk.Label(body, text='送信: 256 MiB・1000項目まで。複数ファイルやフォルダーはZIPで渡します。\n'
                  '受信: 1回32 MiB・20ファイルまで。PCに新しい受信フォルダーを作ります。\n'
                  '接続できないときはWi-Fi、選んだIPv4、ファイアウォールを確認してください。設定は自動変更しません。',
                  wraplength=750, foreground='#555').pack(anchor='w', pady=(10, 0))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after_id = self.after(100, self.poll)

    def draw_qr(self):
        self.canvas.delete('all')
        if self.matrix is None:
            self.canvas.configure(background='white')
            return
        light, dark = ('black', 'white') if self.inverted.get() else ('white', 'black')
        self.canvas.configure(background=light)
        scale = max(1, 300 // len(self.matrix))
        offset = (300 - len(self.matrix) * scale) // 2
        for y, row in enumerate(self.matrix):
            for x, value in enumerate(row):
                if value:
                    x0, y0 = offset + x * scale, offset + y * scale
                    self.canvas.create_rectangle(x0, y0, x0 + scale, y0 + scale, fill=dark, outline='')

    def details(self):
        win = tk.Toplevel(self)
        win.title('HTTPS・ホスト名')
        win.geometry('730x350')
        win.transient(self)
        win.grab_set()
        frame = ttk.Frame(win, padding=15)
        frame.pack(fill='both', expand=True)
        ttk.Checkbutton(frame, text='HTTPSを使用する（証明書と秘密鍵が必要）', variable=self.secure).pack(anchor='w')
        ttk.Label(frame, text='証明書の名前がURLのホスト名またはIPv4と一致し、相手側で信頼されている必要があります。\n'
                  '証明書の自動発行・信頼設定の変更は行いません。暗号化された秘密鍵には対応していません。', wraplength=690).pack(anchor='w', pady=10)
        for label, variable in [('証明書（PEM）', self.certificate), ('秘密鍵（PEM）', self.private_key)]:
            row = ttk.Frame(frame)
            row.pack(fill='x', pady=3)
            ttk.Label(row, text=label, width=16).pack(side='left')
            ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True)
            def choose(var=variable):
                value = filedialog.askopenfilename(parent=win, filetypes=[('PEMファイル', '*.pem *.crt *.key'), ('すべて', '*')])
                if value:
                    var.set(value)
            ttk.Button(row, text='選択', command=choose).pack(side='right')
        ttk.Label(frame, text='ホスト名（空欄は選択したIPv4。このPCに名前解決されるDNS名だけを指定）').pack(anchor='w', pady=(10, 0))
        ttk.Entry(frame, textvariable=self.hostname).pack(fill='x')
        def close():
            win.grab_release()
            win.destroy()
            self.grab_set()
        ttk.Button(frame, text='閉じる', command=close).pack(pady=12)
        win.protocol('WM_DELETE_WINDOW', close)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        if self.owner.worker and self.owner.worker.is_alive():
            return
        try:
            address = bind_address(self.address.get().strip())
            port = int(self.port.get())
            minutes = int(self.minutes.get())
            if not 1 <= minutes <= 60 or port != 0 and not 1024 <= port <= 65535:
                raise ValueError('共有時間は1～60分、ポートは0または1024～65535です。')
            mode = self.mode.get()
            paths = list(self.owner.paths)
            note = self.owner.note.get('1.0', 'end-1c') if mode == 'send' else ''
            destination = self.owner.destination.get()
            force_zip, keep = self.owner.zip.get(), self.keep.get()
            hostname = self.hostname.get().strip()
            certificate = self.certificate.get().strip() if self.secure.get() else ''
            private_key = self.private_key.get().strip() if self.secure.get() else ''
            if self.secure.get() and not (certificate and private_key):
                raise ValueError('HTTPSの証明書と秘密鍵を詳細設定で選んでください。')
            if mode == 'send' and not paths and not note:
                raise ValueError('親画面でファイルを選ぶか、メモを入力してください。')
            if mode == 'send' and paths and note:
                raise ValueError('ファイルとメモは分けて送ってください。')
            if mode == 'receive' and not Path(destination).is_dir():
                raise ValueError('親画面で受信先フォルダーを選んでください。')
        except (ValueError, OSError) as e:
            messagebox.showerror('共有の設定', str(e), parent=self)
            return
        self.cancel.clear()
        self.session = None
        self.folder = ''
        self.return_button.configure(state='disabled')
        self.matrix = None
        self.draw_qr()
        self.url.set('')
        self.copy_button.configure(state='disabled')
        for control in self.controls:
            control.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.status.set('共有を準備しています…')

        def run():
            session = None
            try:
                with tempfile.TemporaryDirectory(prefix='kiwi-browser-selection-') as td:
                    source = prepare(paths, td, self.cancel, note=note, force_zip=force_zip) if mode == 'send' else None
                    # TLS material is loaded locally; no key is sent to native argv or logs.
                    session = Session(native_exe(), mode, source=source, destination=destination,
                                      lifetime=minutes * 60, address=address, port=port, cancel=self.cancel,
                                      hostname=hostname, certificate=certificate, private_key=private_key)
                    self.session = session
                    session.start()
                    self.events.put(('ready', session.url))
                    while not self.cancel.is_set():
                        try:
                            kind, value = session.events.get(timeout=.05)
                        except queue.Empty:
                            continue
                        if kind in ('received', 'sent'):
                            self.events.put((kind, value))
                            if not keep:
                                break
                        elif kind == 'expired':
                            self.events.put((kind, value))
                            break
            except (InterruptedError, TimeoutError):
                pass
            except Exception as e:
                self.events.put(('error', str(e)))
            finally:
                if session:
                    try:
                        session.stop()
                        watch = getattr(session, 'watch', None)
                        if watch:
                            watch.join(timeout=5)
                            if watch.is_alive():
                                raise RuntimeError('共有の監視処理が終了しませんでした。')
                    except Exception as e:
                        self.events.put(('error', '停止処理を確認できませんでした。' + str(e)))
                self.events.put(('done', None))
        self.worker = threading.Thread(target=run, daemon=True)
        self.worker.start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'ready' and not self.cancel.is_set():
                    import qrcode
                    qr = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
                    qr.add_data(value)
                    qr.make(fit=True)
                    self.matrix = qr.get_matrix()
                    self.draw_qr()
                    self.url.set(value)
                    self.copy_button.configure(state='normal')
                    self.status.set('共有中です。このQRまたはURLを相手のスマホで開いてください。')
                elif kind == 'received':
                    self.folder = value
                    self.owner.received = value
                    self.owner.open_button.configure(state='normal')
                    self.return_button.configure(state='normal')
                    self.status.set('受け取りました。親画面から受信フォルダーを開けます。')
                elif kind == 'sent':
                    self.status.set('送信が完了しました。')
                elif kind in ('error', 'expired'):
                    self.status.set(value)
                elif kind == 'done':
                    self.matrix = None
                    self.draw_qr()
                    self.url.set('')
                    self.copy_button.configure(state='disabled')
                    self.stop_button.configure(state='disabled')
                    if self.status.get().startswith(('共有中', '共有を準備', '共有を停止')):
                        self.status.set('共有を終了しました。')
                    for control in self.controls:
                        control.configure(state='normal')
        except queue.Empty:
            pass
        if self.closing and not (self.worker and self.worker.is_alive()):
            self.destroy()
            return
        self.after_id = self.after(100, self.poll)

    def copy_url(self):
        if self.url.get() and self.worker and self.worker.is_alive():
            self.clipboard_clear()
            self.clipboard_append(self.url.get())

    def return_files(self):
        if self.folder and Path(self.folder).is_dir():
            for file in sorted(Path(self.folder).iterdir()):
                if file.is_file() and str(file) not in self.owner.paths:
                    self.owner.paths.append(str(file))
            self.owner.refresh_files()
            self.owner.status.set('ブラウザーで受け取ったファイルを送信一覧へ追加しました。')
            self.return_button.configure(state='disabled')

    def stop(self):
        self.cancel.set()
        self.url.set('')
        self.matrix = None
        self.draw_qr()
        self.copy_button.configure(state='disabled')
        self.status.set('共有を停止しています…')

    def close(self):
        self.closing = True
        if self.worker and self.worker.is_alive():
            self.stop()
        else:
            self.destroy()

    def destroy(self):
        if getattr(self, 'after_id', None):
            self.after_cancel(self.after_id)
            self.after_id = None
        self.grab_release()
        self.owner.browser = None
        owner_closing = self.owner.closing
        super().destroy()
        if owner_closing:
            self.owner.close()
