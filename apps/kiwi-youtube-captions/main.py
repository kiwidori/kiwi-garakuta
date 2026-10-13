"""Browse, search and export public YouTube captions."""
import json,queue,threading,tkinter as tk,webbrowser
from pathlib import Path
from tkinter import ttk,filedialog,messagebox
from network import execute_job
from formats import video_id,clock,matching,render

class App(tk.Tk):
    def __init__(self):
        super().__init__();self.title('きういYouTube字幕');self.geometry('1100x780');self.minsize(850,600)
        self.url=tk.StringVar();self.language=tk.StringVar();self.translation=tk.StringVar(value='翻訳しない');self.proxy=tk.StringVar();self.query=tk.StringVar();self.lo=tk.StringVar();self.hi=tk.StringVar();self.preserve=tk.BooleanVar();self.filtered=tk.BooleanVar();self.timestamps=tk.BooleanVar(value=True);self.format=tk.StringVar(value='TXT');self.status=tk.StringVar(value='YouTubeのURLを入力して、字幕一覧を取得してください。');self.origin=tk.StringVar(value='字幕未取得')
        self.q=queue.Queue();self.cancel=threading.Event();self.worker=None;self.running=False;self.tracks=[];self.loaded_id=None;self.translations=[];self.data=None;self.match_indices=[]
        self._ui();self.url.trace_add('write',self._invalidate);self.protocol('WM_DELETE_WINDOW',self.close);self.after(100,self.poll)
    def _ui(self):
        head=ttk.LabelFrame(self,text='動画と字幕',padding=10);head.pack(fill='x',padx=8,pady=6);head.columnconfigure(1,weight=1)
        ttk.Label(head,text='YouTube URL / 動画ID').grid(row=0,column=0,sticky='w');ttk.Entry(head,textvariable=self.url).grid(row=0,column=1,columnspan=3,sticky='ew',padx=5)
        self.list_button=ttk.Button(head,text='字幕一覧を取得',command=lambda:self.start('list'));self.list_button.grid(row=0,column=4,padx=3)
        ttk.Label(head,text='元の字幕').grid(row=1,column=0,sticky='w');self.language_box=ttk.Combobox(head,textvariable=self.language,state='readonly',width=36);self.language_box.grid(row=1,column=1,sticky='ew',padx=5,pady=6);self.language_box.bind('<<ComboboxSelected>>',self.choose_track)
        ttk.Label(head,text='翻訳先').grid(row=1,column=2,sticky='e');self.translation_box=ttk.Combobox(head,textvariable=self.translation,state='readonly',width=22);self.translation_box.grid(row=1,column=3,padx=5)
        self.fetch_button=ttk.Button(head,text='字幕を取得',command=lambda:self.start('fetch'));self.fetch_button.grid(row=1,column=4)
        ttk.Checkbutton(head,text='字幕の装飾タグを残す',variable=self.preserve).grid(row=2,column=1,sticky='w')
        ttk.Button(head,text='停止',command=self.cancel.set).grid(row=2,column=4)
        extra=ttk.Notebook(self);extra.pack(fill='x',padx=8);search=ttk.Frame(extra,padding=8);settings=ttk.Frame(extra,padding=8);extra.add(search,text='字幕を検索');extra.add(settings,text='接続設定')
        ttk.Label(search,text='含む文字').grid(row=0,column=0);ttk.Entry(search,textvariable=self.query,width=38).grid(row=0,column=1,padx=5)
        ttk.Label(search,text='開始秒').grid(row=0,column=2);ttk.Entry(search,textvariable=self.lo,width=9).grid(row=0,column=3,padx=5)
        ttk.Label(search,text='終了秒（未満）').grid(row=0,column=4);ttk.Entry(search,textvariable=self.hi,width=9).grid(row=0,column=5,padx=5)
        ttk.Button(search,text='絞り込む',command=self.search).grid(row=0,column=6,padx=4);ttk.Button(search,text='解除',command=self.clear_search).grid(row=0,column=7)
        ttk.Label(settings,text='HTTP/HTTPSプロキシ（任意・保存しません）').pack(side='left');ttk.Entry(settings,textvariable=self.proxy,width=55,show='●').pack(side='left',fill='x',expand=True,padx=5)
        ttk.Label(self,textvariable=self.origin,padding=(10,5)).pack(fill='x')
        area=ttk.Frame(self);area.pack(fill='both',expand=True,padx=8,pady=4);area.columnconfigure(0,weight=1);area.rowconfigure(0,weight=1)
        self.tree=ttk.Treeview(area,columns=('time','duration','text'),show='headings',selectmode='extended')
        for key,label,width in [('time','時刻',100),('duration','長さ(秒)',100),('text','字幕',820)]:self.tree.heading(key,text=label);self.tree.column(key,width=width,minwidth=60)
        vertical=ttk.Scrollbar(area,orient='vertical',command=self.tree.yview);horizontal=ttk.Scrollbar(area,orient='horizontal',command=self.tree.xview);self.tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set);self.tree.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew');self.tree.bind('<Double-1>',lambda _:self.open_time())
        controls=ttk.Frame(self,padding=8);controls.pack(fill='x')
        for label,callback in [('選択時刻をYouTubeで開く',self.open_time),('表示中をコピー',self.copy),('一括保存…',self.batch_dialog),('デモ字幕',self.demo)]:ttk.Button(controls,text=label,command=callback).pack(side='left',padx=3)
        save=ttk.Frame(self,padding=8);save.pack(fill='x');ttk.Combobox(save,textvariable=self.format,values=['TXT','SRT','VTT','JSON','CSV'],state='readonly',width=8).pack(side='left')
        ttk.Checkbutton(save,text='検索に一致した全行だけ保存',variable=self.filtered).pack(side='left',padx=8);ttk.Checkbutton(save,text='TXTに時刻を付ける',variable=self.timestamps).pack(side='left',padx=8);ttk.Button(save,text='保存…',command=self.save).pack(side='right')
        ttk.Label(self,textvariable=self.status,padding=(10,4),wraplength=1050).pack(fill='x');ttk.Label(self,text='一覧表示は最大1,000行。保存は全行または検索に一致した全行です。字幕が非公開の動画は取得できません。',padding=(10,4)).pack(fill='x')
    def _invalidate(self,*_):
        self.loaded_id=None;self.tracks=[];self.language_box['values']=[];self.language.set('');self.choose_track()
    def choose_track(self,*_):
        idx=self.language_box.current();self.translations=self.tracks[idx]['translations'] if 0<=idx<len(self.tracks) and self.tracks[idx]['translatable'] else []
        self.translation_box['values']=['翻訳しない']+[f"{t['language']} [{t['language_code']}]" for t in self.translations];self.translation.set('翻訳しない')
    def start(self,mode):
        if self.running or self.worker and self.worker.is_alive():return
        try:
            ident=video_id(self.url.get());options={'url':self.url.get(),'proxy':self.proxy.get()}
            if mode=='fetch':
                idx=self.language_box.current()
                if self.loaded_id!=ident or not 0<=idx<len(self.tracks):raise ValueError('先に字幕一覧を取得して、元の字幕を選んでください。')
                track=self.tracks[idx];dest=self.translation_box.current()-1
                options.update(code=track['code'],generated=track['generated'],translate=self.translations[dest]['language_code'] if dest>=0 else '',preserve=self.preserve.get())
        except (ValueError,IndexError) as error:self.status.set(str(error));return
        self.cancel.clear();self.running=True;self.list_button.config(state='disabled');self.fetch_button.config(state='disabled');self.status.set('字幕一覧を取得中…' if mode=='list' else '字幕を取得中…')
        self.worker=threading.Thread(target=self.job,args=(mode,options),daemon=True);self.worker.start()
    def job(self,mode,options):
        try:self.q.put(('done',mode,execute_job(mode,options,self.cancel),options['url']))
        except Exception as error:self.q.put(('error',str(error)))
    def poll(self):
        try:
            while True:
                item=self.q.get_nowait()
                if item[0]=='progress':self.status.set(item[1])
                elif item[0]=='batchdone':
                    self.status.set(item[1]);self.batch_report(item[2])
                elif item[0]=='error':self.status.set(item[1])
                elif self.cancel.is_set():self.status.set('取得を停止しました。')
                elif item[3]!=self.url.get():self.status.set('入力が変わったため、取得結果を表示しませんでした。')
                elif item[1]=='list':
                    self.tracks=item[2]['tracks'];self.loaded_id=item[2]['video_id'];self.language_box['values']=[f"{t['language']} [{t['code']}] — {'自動' if t['generated'] else '手動'}" for t in self.tracks]
                    if self.tracks:
                        idx=next((i for i,t in enumerate(self.tracks) if t['code']=='ja'),0);self.language_box.current(idx)
                    self.choose_track();self.status.set(f'利用できる字幕: {len(self.tracks)}種類')
                else:
                    self.data=item[2];self.origin.set(f"取得字幕: {self.data['language']} [{self.data['language_code']}] / 元字幕: {'自動' if self.data['is_generated'] else '手動'}"+(' / YouTube翻訳' if self.data.get('source',{}).get('code')!=self.data['language_code'] else '')+f" / 動画ID: {self.data['video_id']}");self.clear_search()
        except queue.Empty:pass
        if (not self.worker or not self.worker.is_alive()) and self.q.empty():self.running=False;self.list_button.config(state='normal');self.fetch_button.config(state='normal')
        self.after(100,self.poll)
    def clear_search(self):self.query.set('');self.lo.set('');self.hi.set('');self.search()
    def search(self):
        if self.data is None:return False
        try:
            lo=float(self.lo.get()) if self.lo.get().strip() else None;hi=float(self.hi.get()) if self.hi.get().strip() else None
            indices=matching(self.data,self.query.get(),lo,hi)
        except ValueError as error:self.status.set(str(error));return False
        self.match_indices=indices;self.tree.delete(*self.tree.get_children())
        for i in indices[:1000]:
            s=self.data['snippets'][i];self.tree.insert('','end',iid=str(i),values=(clock(s['start']),f"{s['duration']:.2f}",s['text'].replace('\n',' ↵ ')))
        self.status.set(f"字幕{len(self.data['snippets'])}行 / 一致{len(indices)}行 / 表示{min(1000,len(indices))}行");return True
    def open_time(self):
        if self.data is None or not self.tree.selection() or not self.data['video_id']:return
        ident=video_id(self.data['video_id']);s=self.data['snippets'][int(self.tree.selection()[0])];webbrowser.open(f'https://www.youtube.com/watch?v={ident}&t={int(s["start"])}')
    def copy(self):
        if self.data is None:return
        ids=self.tree.selection() or self.tree.get_children();text='\n'.join(self.data['snippets'][int(i)]['text'] for i in ids);self.clipboard_clear();self.clipboard_append(text);self.status.set('表示中の字幕をコピーしました。')
    def save(self):
        if self.data is None:return
        if self.filtered.get() and not self.search():return
        data=dict(self.data)
        if self.filtered.get():data['snippets']=[self.data['snippets'][i] for i in self.match_indices]
        timestamps=self.timestamps.get()
        fmt=self.format.get().lower();filename=filedialog.asksaveasfilename(parent=self,defaultextension='.'+fmt,confirmoverwrite=False,filetypes=[(fmt.upper(),'*.'+fmt)])
        if not filename:return
        target=Path(filename)
        if target.exists() and not messagebox.askyesno('保存','ファイルが存在します。上書きしますか？',parent=self):return
        try:target.write_bytes(render(data,fmt,timestamps));self.status.set('字幕を保存しました。')
        except (OSError,ValueError) as error:messagebox.showerror('保存できません',str(error),parent=self)
    def demo(self):
        if self.running:return
        self.data={'video_id':'','language':'デモ字幕（接続しません）','language_code':'ja','is_generated':False,'snippets':[{'start':0.0,'duration':3.0,'text':'今日はコーヒーをいれてみます。'},{'start':3.2,'duration':4.0,'text':'豆は20グラム、お湯は300ミリリットル。'},{'start':7.4,'duration':3.0,'text':'お湯を少しずつ注ぎます。'},{'start':10.6,'duration':4.0,'text':'できあがり。字幕は時刻付きで保存できます。'}]};self.origin.set('デモ字幕 — サンプル文章・ネットワーク接続なし');self.clear_search()
    def batch_dialog(self):
        if self.running or self.worker and self.worker.is_alive():return
        window=tk.Toplevel(self);window.title('複数動画の字幕を保存');window.geometry('670x470');window.transient(self);window.grab_set()
        ttk.Label(window,text='YouTube URL / 動画ID（1行1個、最大20件）').pack(anchor='w',padx=10,pady=6)
        urls=tk.Text(window,height=8);urls.pack(fill='both',expand=True,padx=10)
        row=ttk.Frame(window,padding=10);row.pack(fill='x');langs=tk.StringVar(value='ja,en');preference=tk.StringVar(value='any');translation=tk.StringVar()
        ttk.Label(row,text='優先する言語（カンマ区切り）').grid(row=0,column=0);ttk.Entry(row,textvariable=langs).grid(row=0,column=1)
        ttk.Label(row,text='字幕の種類').grid(row=1,column=0);ttk.Combobox(row,textvariable=preference,values=['any','manual','generated'],state='readonly').grid(row=1,column=1)
        ttk.Label(row,text='翻訳先の言語コード（任意）').grid(row=2,column=0);ttk.Entry(row,textvariable=translation).grid(row=2,column=1)
        ttk.Label(window,text='現在選んでいる保存形式を使います。既存のファイルは上書きしません。').pack(anchor='w',padx=10)
        def start():
            if self.running or self.worker and self.worker.is_alive():return
            try:
                raw=[line.strip() for line in urls.get('1.0','end-1c').splitlines() if line.strip()]
                if not 1<=len(raw)<=20:raise ValueError('動画は1〜20件にしてください。')
                ids=list(dict.fromkeys(video_id(u) for u in raw));languages=[x.strip() for x in langs.get().split(',')]
                from formats import _LANG_RE
                if not 1<=len(languages)<=10 or any(not _LANG_RE.fullmatch(x) for x in languages):raise ValueError('言語コードを1〜10個指定してください。')
                target_lang=translation.get().strip()
                if target_lang and not _LANG_RE.fullmatch(target_lang):raise ValueError('翻訳先の言語コードを確認してください。')
                folder=filedialog.askdirectory(parent=window)
                if not folder:return
                options={'languages':languages,'preference':preference.get(),'translate':target_lang,'preserve':self.preserve.get(),'proxy':self.proxy.get()};fmt=self.format.get().lower();timestamps=self.timestamps.get()
            except ValueError as error:messagebox.showerror('入力',str(error),parent=window);return
            window.destroy();self.cancel.clear();self.running=True;self.list_button.config(state='disabled');self.fetch_button.config(state='disabled');self.status.set('一括取得を開始しました。')
            self.worker=threading.Thread(target=self.batch_job,args=(ids,options,Path(folder),fmt,timestamps),daemon=True);self.worker.start()
        ttk.Button(window,text='保存先を選んで開始',command=start).pack(pady=10)
    def batch_job(self,ids,options,folder,fmt,timestamps):
        report=[];saved=0
        for index,ident in enumerate(ids):
            if self.cancel.is_set():break
            self.q.put(('progress',f'一括取得 {index+1}/{len(ids)}: {ident}'))
            try:
                data=execute_job('fetchauto',{**options,'url':ident},self.cancel)
                if self.cancel.is_set():break
                language=''.join(c for c in data['language_code'] if c.isascii() and (c.isalnum() or c in '-_'))[:40] or 'und'
                target=folder/(ident+'-'+language+'.'+fmt)
                payload=render(data,fmt,timestamps)
                with target.open('xb') as f:f.write(payload)
                saved+=1;report.append(ident+' — 保存しました。')
            except FileExistsError:report.append(ident+' — 同名ファイルがあるため保存しませんでした。')
            except InterruptedError:break
            except Exception as error:report.append(ident+' — '+str(error))
        self.q.put(('batchdone',f'一括取得: 保存{saved}/{len(ids)}件'+('（停止）' if self.cancel.is_set() else ''),'\n'.join(report)))
    def batch_report(self,report):
        window=tk.Toplevel(self);window.title('一括保存の結果');window.geometry('700x350');text=tk.Text(window,wrap='word');text.pack(fill='both',expand=True);text.insert('1.0',report);text.config(state='disabled')

    def close(self):
        self.cancel.set()
        if self.worker and self.worker.is_alive():self.after(50,self.close);return
        for callback in self.tk.splitlist(self.tk.call('after','info')):self.after_cancel(callback)
        self.destroy()

if __name__=='__main__':App().mainloop()
