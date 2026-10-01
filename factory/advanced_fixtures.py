import json
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
PUBLIC=Path('C:/Users/Public/Documents/kiwi-advanced-demo')
PUBLIC.mkdir(exist_ok=True)
(PUBLIC/'入力.json').write_text('{"z":2,"a":"kiwi"}\n',encoding='utf8')
(PUBLIC/'入力.yaml').write_text('name: kiwi\ncount: 2\n',encoding='utf8')
(PUBLIC/'old.py').write_text('def sample():\n    return 1\n',encoding='utf8')
(PUBLIC/'new.py').write_text('def sample():\n    return 2\n',encoding='utf8')
(PUBLIC/'hello.txt').write_text('Hello world\nkiwi apple\n',encoding='utf8')
Image.new('RGB',(32,24),'navy').save(PUBLIC/'画像.png')
CASES={
 'kiwi-search':(['--ignore-case','--count','hello','hello.txt'],b'',lambda b:b'1' in b),
 'kiwi-find':(['--type','directory','--max-depth','1','.','.'],b'',lambda b:True),
 'kiwi-disk':(['--filecount','--depth','1','.'],b'',lambda b:bool(b)),
 'kiwi-json':(['--sort-keys','--compact-output','.','入力.json'],b'',lambda b:b'{"a":"kiwi","z":2}' in b),
 'kiwi-code':(['--language','json','--tabs','4','--color','never','入力.json'],b'',lambda b:b'kiwi' in b),
 'kiwi-system':(['--format','json','--structure','OS:Uptime'],b'',lambda b:any(r['type']=='Uptime' for r in json.loads(b))),
 'kiwi-secrets':(['stdin','--report-format','json','--report-path','-'],b'ordinary non-secret\n',lambda b:json.loads(b)==[]),
 'kiwi-regex':(['--words','--spaces','--no-anchors','-'],b'hello kiwi\nhello world\n',lambda b:b'\\w' in b and not b.startswith(b'^')),
 'kiwi-http':(['--offline','--ignore-stdin','--pretty=none','POST','https://example.com/api','name=kiwi','X-Demo:sample'],b'',lambda b:b'POST' in b and b'kiwi' in b),
 'kiwi-png':(['--strip','safe','--stdout','画像.png'],b'',lambda b:b.startswith(b'\x89PNG\r\n\x1a\n')),
 'kiwi-yaml':(['eval','--output-format','json','.name = "updated"','入力.yaml'],b'',lambda b:json.loads(b)['name']=='updated'),
 'kiwi-hash':(['--length','64','--no-names','hello.txt'],b'',lambda b:len(b.strip())==128),
 'kiwi-color':(['format','oklch','#336699'],b'',lambda b:b'oklch(' in b.lower()),
 'kiwi-ascii':(['--width','24','--flipX','--complex','画像.png'],b'',lambda b:bool(b)),
 'kiwi-space':(['-json','-all','-sort','size'],b'',lambda b:isinstance(json.loads(b),list)),
 'kiwi-diff':(['--color','never','--display','side-by-side','--context','1','old.py','new.py'],b'',lambda b:b'1' in b and b'2' in b),
}
