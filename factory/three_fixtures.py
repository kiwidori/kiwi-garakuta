"""Small public Windows demonstration fixtures, without private user paths."""
from pathlib import Path
import subprocess

PUBLIC = Path('C:/Users/Public/Documents/kiwi-three-demo')
TEXTS = {
    'css': 'body { color: #ffffff; margin: 0px; }',
    'js': 'function add(a, b) { return a + b; } console.log(add(1, 2));',
    'html': '<!doctype html><html><head><title>デモ</title></head><body><!--demo--><p>こんにちは</p></body></html>',
    'json': '{ "hello": "こんにちは", "items": [1, 2, 3] }',
    'svg': '<svg xmlns="http://www.w3.org/2000/svg" width="100"><rect x="0" width="100" height="20" fill="#ffffff" /></svg>',
    'xml': '<?xml version="1.0"?><root> <item name="demo"> Hello </item> </root>',
}


def prepare():
    code, shell, web = [PUBLIC / name for name in ('サンプルコード', 'シェル', 'Web')]
    for folder in (code, shell, web):
        folder.mkdir(parents=True, exist_ok=True)
    (code/'main.py').write_text('# サンプル\n\ndef greet(name):\n    if name:\n        return "Hello " + name\n    return "Hello"\n', encoding='utf8')
    (code/'demo.js').write_text('function greet(name) {\n  return "Hello " + name;\n}\n', encoding='utf8')
    (shell/'hello.sh').write_text('#!/bin/bash\nif true;then\necho "こんにちは"\nfi\n', encoding='utf8')
    for ext, text in TEXTS.items():
        (web/f'demo.{ext}').write_text(text, encoding='utf8')
    (web/'notes.txt').write_text('Copy me for sync test', encoding='utf8')
    (web/'nested').mkdir(exist_ok=True)
    (web/'nested'/'more.css').write_text('p { margin: 0px; }', encoding='utf8')
    if not (code/'.git').exists():
        def git(*args):
            subprocess.run(['git', '-C', str(code), *args], check=True, capture_output=True)
        git('init'); git('config', 'user.name', 'Demo'); git('config', 'user.email', 'demo@example.invalid')
        git('add', '.'); git('commit', '-m', 'Demo sample')
        (code/'demo.js').write_text('function greet(name) {\n  if (name) return "Hello " + name;\n  return "Hello";\n}\n', encoding='utf8')
        git('add', '.'); git('commit', '-m', 'Demo second change')
    return code, shell, web
