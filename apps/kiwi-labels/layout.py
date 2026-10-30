"""Build label documents from validated text and fixed layout choices."""
import json,math,re
def string(value):
 if not isinstance(value,str) or len(value)>120 or any(ord(c)<32 for c in value):raise ValueError('ラベルの1行は制御文字なしの120文字までです。')
 return json.dumps(value,ensure_ascii=False)

def source(items,columns=2,rows=6,margin=10,gap=3,font=20,repeat=1,color='333333',border=True,font_family='Yu Gothic'):
 if not isinstance(font_family,str) or not font_family.strip():raise ValueError('フォントを確認してください。')
 string(font_family)
 for v,lo,hi in [(columns,1,4),(rows,1,12),(margin,5,25),(gap,0,10),(font,8,32),(repeat,1,100)]:
  if type(v) is not int or not lo<=v<=hi:raise ValueError('配置の指定範囲を確認してください。')
 if not isinstance(border,bool) or not __import__('re').fullmatch('[0-9A-Fa-f]{6}',color):raise ValueError('枠・色を確認してください。')
 if not items or len(items)>200 or len(items)*repeat>400:raise ValueError('ラベルは1～200種類、複製後400枚までです。')
 values=[]
 for lines in items:
  if not isinstance(lines,(list,tuple)) or not 1<=len(lines)<=3 or not any(x.strip() for x in lines):raise ValueError('1枚につき1～3行の文字を入れてください。')
  values.extend([lines]*repeat)
 width=(210-2*margin-gap*(columns-1))/columns;height=(297-2*margin-gap*(rows-1))/rows
 if width<25 or height<15:raise ValueError('ラベルが小さすぎます。列・行・余白・間隔を調整してください。')
 per=columns*rows;pages=math.ceil(len(values)/per)
 if pages>10:raise ValueError('10ページ以内になるよう配置してください。')
 pre=f'''#set page(width: 210mm, height: 297mm, margin: {margin}mm)
#set document(title: "Labels", author: (), date: auto)
#set text(font: {string(font_family)}, lang: "ja", size: {font}pt, fill: rgb("{color}"))
#let card(lines) = context {{
  let body = stack(dir: ttb, spacing: 2pt, ..lines.map(line => text(line)))
  let m = measure(body)
  let ratio = calc.min(1, {width-6:.8f}mm / calc.max(m.width, 1pt), {height-6:.8f}mm / calc.max(m.height, 1pt))
  rect(width: {width:.8f}mm, height: {height:.8f}mm, inset: 0pt, radius: 1mm, stroke: {('0.3pt + rgb("'+color+'")') if border else 'none'})[
    #place(center + horizon, scale(x: ratio * 100%, y: ratio * 100%, reflow: true, body))
  ]
}}
'''
 parts=[pre]
 for start in range(0,len(values),per):
  if start:parts.append('#pagebreak()\n')
  cells=['card(('+','.join(string(x) for x in lines)+',))' for lines in values[start:start+per]]
  parts.append(f'#grid(columns: ({",".join(["1fr"]*columns)},), rows: {height:.8f}mm, gutter: {gap}mm, '+','.join(cells)+')\n')
 return ''.join(parts),pages
