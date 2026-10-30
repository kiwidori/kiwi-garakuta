"""Run image operations in a disposable, bounded worker process."""
import json,multiprocessing,time,traceback
from pathlib import Path

def describe(error):
 frames=' > '.join(Path(f.filename).name+':'+str(f.lineno) for f in traceback.extract_tb(error.__traceback__)[-6:])
 return (type(error).__name__+' ['+frames+']: '+str(error).replace('\n',' | ').replace('\r','').replace('\x00',''))[:4000]

def worker(pipe,task):
 try:
  from ocr_engine import execute
  packet={'ok':True,'result':execute(task)}
 except Exception as e:packet={'ok':False,'error':describe(e)}
 try:
  raw=json.dumps(packet,ensure_ascii=True).encode('utf8')
  if len(raw)>32*1024*1024:raw=json.dumps({'ok':False,'error':'処理結果が32 MiBを超えました。'}).encode()
  pipe.send_bytes(raw)
 finally:pipe.close()

def run(task,cancel,timeout=120):
 if cancel.is_set():raise InterruptedError('停止しました。')
 if len(json.dumps(task).encode('utf8'))>16*1024*1024:raise ValueError('入力が大きすぎます。')
 ctx=multiprocessing.get_context('spawn');recv,send=ctx.Pipe(duplex=False);process=ctx.Process(target=worker,args=(send,task),daemon=True);started=False
 try:
  process.start();started=True;send.close();deadline=time.monotonic()+timeout
  while True:
   if cancel.is_set():raise InterruptedError('停止しました。')
   if time.monotonic()>deadline:raise TimeoutError('120秒の上限に達しました。画像や内容を小さくしてください。')
   if recv.poll(.03):
    packet=json.loads(recv.recv_bytes(32*1024*1024));break
   if not process.is_alive():raise RuntimeError('画像処理が終了しました。結果を受け取れませんでした。')
  process.join(timeout=1)
  if process.is_alive():raise RuntimeError('画像処理を正常終了できませんでした。')
  if cancel.is_set():raise InterruptedError('停止しました。')
  if not packet.get('ok'):raise ValueError(packet.get('error','処理に失敗しました。'))
  return packet['result']
 finally:
  if started:
   if process.is_alive():process.terminate()
   process.join(timeout=2)
   if process.is_alive():process.kill();process.join()
   process.close()
  recv.close();send.close()
