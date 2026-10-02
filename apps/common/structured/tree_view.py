from urllib.parse import unquote
from collections import deque
from tkinter import ttk, filedialog, messagebox
import tkinter as tk
import json
MAX_INPUT = 16 * 1024 * 1024
MAX_NODES = 20000
MAX_DEPTH = 80
PREVIEW_LEN = 120

class Number(str):
    pass

def _parse_int(s):
    return Number(s)

def _parse_float(s):
    return Number(s)

def dump_json(value, indent=2):

    def _dump(obj, level=0):
        indent_str = '  ' * level
        next_indent = '  ' * (level + 1)
        if isinstance(obj, dict):
            if not obj:
                return '{}'
            items = []
            for k, v in obj.items():
                key_str = json.dumps(k)
                val_str = _dump(v, level + 1)
                items.append(f'{next_indent}{key_str}: {val_str}')
            return '{\n' + ',\n'.join(items) + '\n' + indent_str + '}'
        if isinstance(obj, list):
            if not obj:
                return '[]'
            items = []
            for v in obj:
                val_str = _dump(v, level + 1)
                items.append(f'{next_indent}{val_str}')
            return '[\n' + ',\n'.join(items) + '\n' + indent_str + ']'
        if isinstance(obj, Number):
            return str(obj)
        if obj is None:
            return 'null'
        if obj is True:
            return 'true'
        if obj is False:
            return 'false'
        if isinstance(obj, (int, float)):
            return json.dumps(obj)
        if isinstance(obj, str):
            return json.dumps(obj)
        raise TypeError(f'Object of type {type(obj)} is not JSON serializable')
    return _dump(value)

def parse_documents(data: bytes):
    if len(data) > MAX_INPUT:
        raise ValueError('Input exceeds 16MiB limit')
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as e:
        raise ValueError(f'Invalid UTF-8 encoding: {e}')

    def _reject_constant(c):
        raise ValueError(f'Non-finite number not allowed: {c}')
    decoder = json.JSONDecoder(parse_int=_parse_int, parse_float=_parse_float, strict=True, parse_constant=_reject_constant)
    docs = []
    idx = 0
    length = len(text)
    total_nodes = 0
    while idx < length:
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length:
            break
        try:
            obj, end_idx = decoder.raw_decode(text, idx)
        except json.JSONDecodeError as e:
            raise ValueError(f'JSON parse error at index {idx}: {e}')
        stack = [(obj, 0)]
        doc_nodes = 0
        while stack:
            node, depth = stack.pop()
            if depth > MAX_DEPTH:
                raise ValueError(f'Depth exceeds {MAX_DEPTH}')
            doc_nodes += 1
            total_nodes += 1
            if total_nodes > MAX_NODES:
                raise ValueError(f'Node count exceeds {MAX_NODES}')
            if isinstance(node, dict):
                for v in node.values():
                    stack.append((v, depth + 1))
            elif isinstance(node, list):
                for v in node:
                    stack.append((v, depth + 1))
        docs.append(obj)
        idx = end_idx
    if not docs:
        raise ValueError('No JSON documents found')
    return docs

class TreeWindow(tk.Toplevel):

    def __init__(self, parent, data: bytes):
        super().__init__(parent)
        self.title('JSONツリー')
        self.geometry('1120x850')
        self.parent = parent
        self.original_data = data
        self.docs = []
        self.records = {}
        self.tree = None
        self.text_widget = None
        self.history_back = deque()
        self.history_forward = deque()
        self.current_path = None
        self.search_results = []
        self.search_index = -1
        try:
            self.docs = parse_documents(data)
        except Exception as e:
            messagebox.showerror('JSONを読めません', str(e))
            self.destroy()
            return
        self._build_ui()
        self._extra_controls()
        self._rebuild_tree(doc_index=0)

    def _build_ui(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        doc_label = ttk.Label(top_frame, text='文書:')
        doc_label.pack(side=tk.LEFT)
        self.doc_var = tk.StringVar()
        self.doc_combo = ttk.Combobox(top_frame, textvariable=self.doc_var, state='readonly', width=10)
        self.doc_combo.pack(side=tk.LEFT, padx=5)
        self._update_doc_combo()
        self.doc_combo.bind('<<ComboboxSelected>>', self._on_doc_select)
        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(search_frame, text='文字を検索:').pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind('<Return>', lambda e: self._search_next())
        ttk.Button(search_frame, text='次へ', command=self._search_next).pack(side=tk.LEFT, padx=2)
        ttk.Button(search_frame, text='前へ', command=self._search_prev).pack(side=tk.LEFT, padx=2)
        nav_frame = ttk.Frame(self)
        nav_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(nav_frame, text='すべて展開', command=self._expand_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text='すべて折り畳む', command=self._collapse_all).pack(side=tk.LEFT, padx=2)
        level_label = ttk.Label(nav_frame, text='展開する深さ:')
        level_label.pack(side=tk.LEFT, padx=(10, 2))
        self.level_var = tk.IntVar(value=1)
        self.level_spin = ttk.Spinbox(nav_frame, from_=0, to=80, textvariable=self.level_var, width=5)
        self.level_spin.pack(side=tk.LEFT)
        ttk.Button(nav_frame, text='適用', command=self._set_level).pack(side=tk.LEFT, padx=2)
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(action_frame, text='キーをコピー', command=self._copy_key).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text='値をコピー', command=self._copy_value).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text='パスをコピー', command=self._copy_path).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text='選択値を保存', command=self._save_json).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text='表示から削除', command=self._delete_node).pack(side=tk.RIGHT, padx=2)
        ttk.Button(action_frame, text='元に戻す', command=self._reset_original).pack(side=tk.RIGHT, padx=2)
        goto_frame = ttk.Frame(self)
        goto_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(goto_frame, text='パスへ移動:').pack(side=tk.LEFT)
        self.goto_var = tk.StringVar()
        self.goto_entry = ttk.Entry(goto_frame, textvariable=self.goto_var, width=40)
        self.goto_entry.pack(side=tk.LEFT, padx=5)
        self.goto_entry.bind('<Return>', lambda e: self._goto_path())
        ttk.Button(goto_frame, text='移動', command=self._goto_path).pack(side=tk.LEFT, padx=2)
        hist_frame = ttk.Frame(self)
        hist_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(hist_frame, text='戻る', command=self._history_back).pack(side=tk.LEFT, padx=2)
        ttk.Button(hist_frame, text='進む', command=self._history_forward).pack(side=tk.LEFT, padx=2)
        pane = ttk.PanedWindow(self, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        tree_frame = ttk.Frame(pane)
        pane.add(tree_frame, weight=1)
        self.tree = ttk.Treeview(tree_frame, columns=('type', 'value', 'size', 'row'), show='tree headings')
        self.tree.heading('#0', text='項目')
        self.tree.heading('type', text='型')
        self.tree.heading('value', text='値のプレビュー')
        self.tree.heading('size', text='項目数／文字数')
        self.tree.heading('row', text='項目番号')
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind('<<TreeviewSelect>>', self._on_select)
        text_frame = ttk.Frame(pane)
        pane.add(text_frame, weight=1)
        self.text_widget = tk.Text(text_frame, wrap=tk.WORD, state=tk.DISABLED, height=10)
        text_scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.text_widget.yview)
        self.text_widget.configure(yscrollcommand=text_scrollbar.set)
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        text_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _update_doc_combo(self):
        self.doc_combo['values'] = [f'文書 {i + 1}' for i in range(len(self.docs))]
        if self.docs:
            self.doc_var.set('文書 1')

    def _on_doc_select(self, event=None):
        idx = self.doc_combo.current()
        if idx >= 0 and idx < len(self.docs):
            self._rebuild_tree(doc_index=idx)

    def _rebuild_tree(self, doc_index=0):
        if not self.docs:
            return
        self.history_back.clear()
        self.history_forward.clear()
        self.current_path = None
        self.tree.delete(*self.tree.get_children())
        self.records.clear()
        self._row_counter = 0
        doc = self.docs[doc_index]
        root_iid = f'n{len(self.records)}'
        self._insert_node('', '', doc, 0, doc_index, [], [])

    def _insert_node(self, parent_iid, key, value, depth, doc_index, path_keys, path_indices):
        if isinstance(value, dict):
            type_str = 'object'
        elif isinstance(value, list):
            type_str = 'array'
        elif isinstance(value, bool):
            type_str = 'boolean'
        elif value is None:
            type_str = 'null'
        elif isinstance(value, Number):
            type_str = 'number'
        elif isinstance(value, (int, float)):
            type_str = 'number'
        else:
            type_str = 'string'
        if isinstance(value, (dict, list)):
            size = len(value)
        else:
            size = len(str(value))
        preview = self._get_preview(value)
        self._row_counter += 1
        row_num = self._row_counter
        expr_path = self._build_expr_path(path_keys, path_indices)
        json_pointer = self._build_json_pointer(path_keys, path_indices)
        iid = f'n{len(self.records)}'
        display_key = key if key else '文書のルート'
        self.tree.insert(parent_iid, 'end', iid=iid, text=display_key, values=(type_str, preview, size, row_num))
        self.records[iid] = {'value': value, 'key': key, 'parent': parent_iid, 'doc_index': doc_index, 'expr_path': expr_path, 'json_pointer': json_pointer, 'path_keys': path_keys.copy(), 'path_indices': path_indices.copy()}
        if isinstance(value, dict):
            for k, v in value.items():
                self._insert_node(iid, k, v, depth + 1, doc_index, path_keys + [k], path_indices + [None])
        elif isinstance(value, list):
            for i, v in enumerate(value):
                self._insert_node(iid, str(i), v, depth + 1, doc_index, path_keys + [''], path_indices + [i])

    def _get_preview(self, value):
        if isinstance(value, dict):
            return f'{{{len(value)}項目}}'
        elif isinstance(value, list):
            return f'[{len(value)}項目]'
        s = str(value)
        if len(s) > PREVIEW_LEN:
            return s[:PREVIEW_LEN] + '...'
        return s

    def _build_expr_path(self, keys, indices):
        if not keys:
            return 'x'
        out = 'x'
        for k, i in zip(keys, indices):
            if isinstance(i, int):
                out += f'[{i}]'
            else:
                out += '[' + json.dumps(k, ensure_ascii=False) + ']'
        return out

    def _build_json_pointer(self, keys, indices):
        if not keys:
            return ''
        parts = []
        for k, i in zip(keys, indices):
            if isinstance(i, int):
                parts.append(str(i))
            else:
                parts.append(str(k).replace('~', '~0').replace('/', '~1'))
        return '/' + '/'.join(parts)

    def _on_select(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        record = self.records.get(iid)
        if not record:
            return
        new_path = record['expr_path']
        if self.current_path != new_path:
            if self.current_path is not None:
                self.history_back.append(self.current_path)
            self.history_forward.clear()
            self.current_path = new_path
        self.text_widget.configure(state=tk.NORMAL)
        self.text_widget.delete('1.0', tk.END)
        try:
            full_value = dump_json(record['value'])
        except Exception as e:
            full_value = f'Error dumping value: {e}'
        self.text_widget.insert(tk.END, full_value)
        self.text_widget.configure(state=tk.DISABLED)

    def _expand_all(self):
        for iid in self.tree.get_children(''):
            self._expand_subtree(iid, True)

    def _expand_subtree(self, parent_iid, open_state=True):
        for child in self.tree.get_children(parent_iid):
            if self.tree.get_children(child):
                self.tree.item(child, open=open_state)
                self._expand_subtree(child, open_state)

    def _collapse_all(self):
        for iid in self.tree.get_children(''):
            self._expand_subtree(iid, False)

    def _set_level(self):
        try:
            level = int(self.level_var.get())
        except (ValueError, tk.TclError):
            messagebox.showerror('Level Error', 'Invalid level number')
            return
        if level < 0 or level > 80:
            messagebox.showerror('Level Error', f'Level must be between 0 and 80')
            return
        self._collapse_all()

        def expand_to_level(parent_iid, current_depth):
            for child in self.tree.get_children(parent_iid):
                if current_depth < level:
                    self.tree.item(child, open=True)
                    if self.tree.get_children(child):
                        expand_to_level(child, current_depth + 1)
        root_children = self.tree.get_children('')
        for rc in root_children:
            self.tree.item(rc, open=True)
            if level > 0 and self.tree.get_children(rc):
                expand_to_level(rc, 1)

    def _search_next(self):
        query = self.search_var.get().casefold()
        if not query:
            return
        matches = []
        for iid, record in self.records.items():
            key_str = str(record['key']).casefold()
            value_str = str(record['value']).casefold()
            path_str = record['expr_path'].casefold()
            if query in key_str or query in value_str or query in path_str:
                matches.append(iid)
        self.search_results = matches
        if not matches:
            messagebox.showinfo('検索', '見つかりませんでした。')
            return
        current_selection = self.tree.selection()
        current_iid = current_selection[0] if current_selection else None
        if current_iid in matches:
            idx = matches.index(current_iid)
            next_idx = (idx + 1) % len(matches)
        else:
            next_idx = 0
        target_iid = matches[next_idx]
        self.tree.selection_set(target_iid)
        self.tree.see(target_iid)

    def _search_prev(self):
        query = self.search_var.get().casefold()
        if not query:
            return
        matches = []
        for iid, record in self.records.items():
            key_str = str(record['key']).casefold()
            value_str = str(record['value']).casefold()
            path_str = record['expr_path'].casefold()
            if query in key_str or query in value_str or query in path_str:
                matches.append(iid)
        self.search_results = matches
        if not matches:
            messagebox.showinfo('検索', '見つかりませんでした。')
            return
        current_selection = self.tree.selection()
        current_iid = current_selection[0] if current_selection else None
        if current_iid in matches:
            idx = matches.index(current_iid)
            prev_idx = (idx - 1) % len(matches)
        else:
            prev_idx = len(matches) - 1
        target_iid = matches[prev_idx]
        self.tree.selection_set(target_iid)
        self.tree.see(target_iid)

    def _copy_key(self):
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        record = self.records.get(iid)
        if record:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(str(record['key']))

    def _copy_value(self):
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        record = self.records.get(iid)
        if record:
            try:
                val_str = dump_json(record['value'])
                self.parent.clipboard_clear()
                self.parent.clipboard_append(val_str)
            except Exception as e:
                messagebox.showerror('Copy Error', str(e))

    def _copy_path(self):
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        record = self.records.get(iid)
        if record:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(record['expr_path'])

    def _save_json(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo('保存', '項目を選択してください。')
            return
        iid = selection[0]
        record = self.records.get(iid)
        if not record:
            return
        try:
            json_str = dump_json(record['value'])
        except Exception as e:
            messagebox.showerror('保存できません', str(e))
            return
        filename = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON files', '*.json'), ('All files', '*.*')])
        if not filename:
            return
        import os
        if os.path.exists(filename):
            messagebox.showerror('保存できません', '同名のファイルがあります。別の名前を選んでください。')
            return
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(json_str)
            messagebox.showinfo('保存', f'{filename} に保存しました。')
        except Exception as e:
            messagebox.showerror('保存できません', str(e))

    def _delete_node(self):
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        record = self.records.get(iid)
        if not record:
            return
        if messagebox.askyesno('表示から削除', 'この項目を表示から削除しますか？元ファイルは変わりません。'):
            doc_index = record['doc_index']
            parent_iid = record['parent']
            if parent_iid == '':
                self.docs.pop(doc_index)
                if not self.docs:
                    self.tree.delete(*self.tree.get_children())
                    self.records.clear()
                    self._update_doc_combo()
                    return
                self._update_doc_combo()
                new_idx = min(doc_index, len(self.docs) - 1)
                self.doc_var.set(f'文書 {new_idx + 1}')
                self._rebuild_tree(doc_index=new_idx)
            else:
                parent_record = self.records.get(parent_iid)
                if parent_record:
                    parent_value = parent_record['value']
                    key = record['key']
                    if isinstance(parent_value, dict):
                        parent_value.pop(key, None)
                    elif isinstance(parent_value, list):
                        try:
                            idx = int(key)
                            if 0 <= idx < len(parent_value):
                                parent_value.pop(idx)
                        except ValueError:
                            pass

                def remove_subtree(iid_to_remove):
                    for child in self.tree.get_children(iid_to_remove):
                        remove_subtree(child)
                    self.tree.delete(iid_to_remove)
                    if iid_to_remove in self.records:
                        del self.records[iid_to_remove]
                remove_subtree(iid)
                self._rebuild_tree(doc_index=doc_index)

    def _reset_original(self):
        if not messagebox.askyesno('元に戻す', '表示を読み込み直後の状態へ戻しますか？'):
            return
        try:
            self.docs = parse_documents(self.original_data)
        except Exception as e:
            messagebox.showerror('復元できません', str(e))
            return
        self._update_doc_combo()
        self.doc_var.set('文書 1')
        self._rebuild_tree(doc_index=0)

    def _goto_path(self, path_str=None):
        if path_str is None:
            path_str = self.goto_var.get().strip()
        if not path_str:
            return
        target_iid = None
        for iid, record in self.records.items():
            if record['expr_path'] == path_str or record['json_pointer'] == path_str:
                target_iid = iid
                break
        if target_iid is None and path_str.startswith('#'):
            unquoted = unquote(path_str[1:])
            for iid, record in self.records.items():
                if record['json_pointer'] == unquoted:
                    target_iid = iid
                    break
        if target_iid:
            ancestors = []
            current = target_iid
            while current and current != '':
                ancestors.append(current)
                current = self.tree.parent(current)
            for anc in reversed(ancestors):
                if self.tree.exists(anc):
                    self.tree.item(anc, open=True)
            self.tree.selection_set(target_iid)
            self.tree.see(target_iid)
        else:
            messagebox.showerror('移動', f'Path not found: {path_str}')

    def _history_back(self):
        if not self.history_back:
            return
        prev = self.history_back.pop()
        if self.current_path is not None:
            self.history_forward.append(self.current_path)
        self.current_path = prev
        self._goto_path(prev)

    def _history_forward(self):
        if not self.history_forward:
            return
        next_path = self.history_forward.pop()
        if self.current_path is not None:
            self.history_back.append(self.current_path)
        self.current_path = next_path
        self._goto_path(next_path)

    def _move_sibling(self, direction):
        selection = self.tree.selection()
        if not selection:
            return
        iid = selection[0]
        parent_iid = self.tree.parent(iid)
        siblings = self.tree.get_children(parent_iid)
        if not siblings:
            return
        idx = siblings.index(iid)
        new_idx = idx + direction
        if 0 <= new_idx < len(siblings):
            target_iid = siblings[new_idx]
            self.tree.selection_set(target_iid)
            self.tree.see(target_iid)

    def _extra_controls(self):
        extra_frame = ttk.Frame(self)
        extra_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(extra_frame, text='項目番号:').pack(side=tk.LEFT)
        self.row_var = tk.IntVar(value=1)
        self._row_spin = ttk.Spinbox(extra_frame, from_=1, to=20000, textvariable=self.row_var, width=6)
        self._row_spin.pack(side=tk.LEFT, padx=2)
        ttk.Button(extra_frame, text='番号へ移動', command=self._goto_row).pack(side=tk.LEFT, padx=2)
        ttk.Label(extra_frame, text='参照:').pack(side=tk.LEFT, padx=(10, 0))
        self.ref_var = tk.StringVar()
        self.ref_entry = ttk.Entry(extra_frame, textvariable=self.ref_var, width=30)
        self.ref_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(extra_frame, text='参照先へ', command=self._goto_ref).pack(side=tk.LEFT, padx=2)
        self.wrap_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(extra_frame, text='折り返す', variable=self.wrap_var, command=self._toggle_wrap).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(extra_frame, text='前の兄弟', command=lambda: self._move_sibling(-1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(extra_frame, text='次の兄弟', command=lambda: self._move_sibling(1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(extra_frame, text='選択した枝を展開', command=lambda: self._selected_open(True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(extra_frame, text='選択した枝を折り畳む', command=lambda: self._selected_open(False)).pack(side=tk.LEFT, padx=2)

    def _goto_row(self, row_var=None):
        if row_var is None:
            row_var = self.row_var
        try:
            row = int(row_var.get())
        except (tk.TclError, ValueError) as e:
            messagebox.showerror('行移動エラー', f'無効な行番号です: {e}')
            return
        if row < 1 or row > len(self.records):
            messagebox.showerror('行移動エラー', f'行番号が範囲外です (1-{len(self.records)})')
            return
        iid = list(self.records.keys())[row - 1]
        self.tree.selection_set(iid)
        self.tree.see(iid)

    def _goto_ref(self, ref_var=None):
        if ref_var is None:
            ref_var = self.ref_var
        ref_str = ref_var.get().strip()
        if not ref_str:
            sel = self.tree.selection()
            if not sel:
                messagebox.showerror('参照エラー', '選択されたノードがありません')
                return
            record = self.records.get(sel[0])
            if not record:
                return
            val = record['value']
            if isinstance(val, str):
                ref_str = val.strip()
            elif isinstance(val, dict) and '$ref' in val and isinstance(val['$ref'], str):
                ref_str = val['$ref'].strip()
        if not ref_str.startswith('#'):
            messagebox.showerror('参照エラー', '外部参照はサポートされていません。#で始まるJSON Pointerが必要です')
            return
        self._goto_path(ref_str)

    def _toggle_wrap(self, wrap_var=None):
        if wrap_var is None:
            wrap_var = self.wrap_var
        mode = 'word' if wrap_var.get() else 'none'
        self.text_widget.configure(wrap=mode)

    def _selected_open(self, opened=True):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        self.tree.item(iid, open=opened)
        self._expand_subtree(iid, opened)
