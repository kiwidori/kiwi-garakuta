"""PDF marks in the editor's Tk interpreter, sharing input and results."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import stamp_core as core

class StampDialog(tk.Toplevel):
    def __init__(self,parent,path,pages=''):
        super().__init__(parent)
        self.owner=parent;self.closing=False;self.controls=[];self.vars={};self.traces=[];self.result=None
        self.title('PDFに文字・ロゴを重ねる');self.geometry('1060x920');self.minsize(1000,860)
        self.body=ttk.Frame(self,padding=14);self.body.pack(fill='both',expand=True)
        ttk.Label(self.body,text='PDFに文字・ロゴを重ねる',font=('Yu Gothic UI',18,'bold')).pack(anchor='w')
        ttk.Label(self.body,text='選択したPDFや編集結果をそのまま使えます。保存後は表示確認・次の編集へ。').pack(anchor='w',pady=8)
        self.button(self.body,'スタンプエンジンを準備（初回のみ）',self.setup).pack(anchor='w',pady=6)
        self.form=ttk.Frame(self.body);self.form.pack(fill='x');self.form.columnconfigure(1,weight=1);self.row=0
        self.field('input','元のPDF',str(path),picker=[('PDF','*.pdf')])
        self.field('action','操作','追加',['追加','更新','削除'])
        self.field('layer','重ね方','手前（スタンプ）',['手前（スタンプ）','背面（透かし）'])
        self.field('kind','重ねる内容','日本語の文字（画像化）',['日本語の文字（画像化）','欧文・ページ番号','画像','PDFの指定ページ','PDFを順番に重ねる'])
        self.field('text','文字（改行は \\n、欧文のページ番号は %p / %P）','確認用')
        self.field('mark','ロゴ画像／重ねるPDF','',picker=[('画像・PDF','*.png *.jpg *.jpeg *.webp *.tif *.tiff *.pdf')])
        self.field('markpage','重ねるPDFのページ／順番の開始（例 2:3）','1')
        self.field('pages','対象ページ（空欄は全部、1-3,5 / odd / even）',pages)
        self.field('position','位置','中央',list(core.POSITIONS))
        self.field('scale','大きさ（通常0.01～1、絶対指定は100まで）','0.5')
        self.field('rotation','回転（-180～180度）','-30')
        self.field('opacity','濃さ（0.01～1）','0.3')
        self.field('extra','詳細設定（欧文・画像・PDF用JSON）','{}')
        row=ttk.Frame(self.body);row.pack(fill='x',pady=10)
        self.button(row,'別名でPDFを保存（F5）',self.process).pack(side='left')
        self.preview_button=self.button(row,'保存PDFを表示・画像化',self.preview);self.preview_button.pack(side='left',padx=8)
        self.edit_button=self.button(row,'保存PDFを編集一覧へ追加',self.edit_result);self.edit_button.pack(side='left')
        self.button(row,'ヘルプ',self.help).pack(side='right')
        self.button(row,'エンジン情報',self.version).pack(side='right',padx=6)
        self.output=tk.Text(self.body,height=5,wrap='word',state='disabled');self.output.pack(fill='both',expand=True)
        row=ttk.Frame(self.body);row.pack(fill='x',pady=8)
        self.stop=ttk.Button(row,text='停止',state='disabled',command=parent.stop);self.stop.pack(side='left')
        self.status=tk.StringVar(master=self,value='元のPDFを残して別名で保存します。')
        ttk.Label(row,textvariable=self.status,wraplength=900).pack(side='left',padx=8)
        ttk.Label(self.body,text='元PDF32 MiB・1000ページ、画像等16 MiBまで。暗号化・電子署名付きPDFは対象外です。\n透かしはコピー・編集を防ぎません。日本語は画像化され、文字の選択・検索はできません。',wraplength=1000).pack(anchor='w')
        for var in self.vars.values():self.traces.append((var,var.trace_add('write',self.invalidate)))
        self.set_busy(False);self.protocol('WM_DELETE_WINDOW',self.close)
        self.bind('<F5>',lambda event:self.process());self.bind('<Alt-F4>',lambda event:(self.close(),'break')[1])

    def button(self,parent,text,command):
        button=ttk.Button(parent,text=text,command=command);self.controls.append((button,'normal'));return button

    def field(self,key,label,value,choices=None,picker=None):
        var=tk.StringVar(master=self,value=value);self.vars[key]=var
        ttk.Label(self.form,text=label).grid(row=self.row,column=0,sticky='w',pady=4,padx=(0,12))
        state='readonly' if choices else 'normal'
        widget=ttk.Combobox(self.form,textvariable=var,values=choices,state=state) if choices else ttk.Entry(self.form,textvariable=var)
        widget.grid(row=self.row,column=1,sticky='ew',pady=4);self.controls.append((widget,state))
        if picker:
            def pick():
                if self.owner.busy():return
                path=filedialog.askopenfilename(parent=self,filetypes=picker)
                if path:var.set(path)
            self.button(self.form,'選ぶ…',pick).grid(row=self.row,column=2,padx=(8,0))
        self.row+=1

    def values(self):return {key:var.get() for key,var in self.vars.items()}

    def show(self,text):
        self.output.configure(state='normal');self.output.delete('1.0','end');self.output.insert('1.0',text[:65536]);self.output.configure(state='disabled')

    def invalidate(self,*args):
        self.result=None;self.show('設定を変更しました。新しいPDFを保存してから表示・編集へ渡してください。')
        self.preview_button.configure(state='disabled');self.edit_button.configure(state='disabled')

    def set_busy(self,busy):
        for widget,state in self.controls:widget.configure(state='disabled' if busy else state)
        self.stop.configure(state='normal' if busy else 'disabled')
        if busy or not self.result:self.preview_button.configure(state='disabled');self.edit_button.configure(state='disabled')

    def setup(self):
        self.owner.start_stamp(lambda:core.ENGINE.install(self.owner.cancel,lambda text:self.owner.stamp_events.put(('progress',text))),lambda _:self.status.set('スタンプエンジンを準備しました。'))

    def process(self):
        if self.owner.busy():return
        values=self.values();values['text']=values['text'].replace('\\n','\n')
        if values['action'] in {'更新','削除'} and not messagebox.askyesno('操作の確認','pdfcpu形式の既存の印を対象ページから取り除きます。続けますか？',parent=self):return
        folder=filedialog.askdirectory(parent=self,title='スタンプPDFの保存先フォルダー')
        if not folder:return
        self.invalidate()
        self.owner.start_stamp(lambda:core.run(values,folder,self.owner.cancel),self.receive)

    def receive(self,result):
        self.result=result;self.owner.last_output=result['path']
        self.show(f"保存しました: {Path(result['path']).name}\n{result['pages']}ページ / {result['bytes']:,} bytes\n「保存PDFを表示・画像化」で見た目を確認できます。元のPDFは変更していません。")
        self.status.set('保存しました。表示確認や次の編集へ渡せます。');self.set_busy(False)

    def preview(self):
        if not self.owner.busy() and self.result:
            if self.owner.show_image_path(self.result['path']) is None:self.status.set(self.owner.status_var.get())

    def edit_result(self):
        if not self.owner.busy() and self.result:
            self.owner.add_paths([self.result['path']]);self.status.set('保存したPDFを編集一覧に追加しました。')

    def version(self):self.owner.start_stamp(lambda:core.version(self.owner.cancel),self.show)

    def help(self):
        top=tk.Toplevel(self);top.title('PDFスタンプのヘルプ');top.geometry('850x680')
        text=tk.Text(top,wrap='word');text.pack(fill='both',expand=True)
        text.insert('1.0',(core.ROOT/'README.txt').read_text(encoding='utf8')+'\n\n'+(core.ROOT/'upstream-help.txt').read_text(encoding='utf8'));text.configure(state='disabled')

    def close(self):
        if self.owner.stamp_worker is not None:
            self.closing=True;self.owner.stop();self.status.set('停止してから閉じます…')
        else:self.destroy();self.owner.stamp_dialog=None

    def destroy(self):
        for var,token in self.traces:var.trace_remove('write',token)
        self.traces.clear();self.vars.clear();self.status=None
        super().destroy();self.controls.clear()
