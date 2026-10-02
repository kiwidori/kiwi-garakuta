"""Windows regression checks for the gron wrapper's input and native operations."""
import sys,json,tempfile,threading,http.server,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'apps/common'));sys.path.insert(0,str(ROOT/'apps/kiwi-json-paths'))
from gron_job import build_request,execute_job,normalize_values
EXE=ROOT/'.tools/kiwi-json-paths/gron.exe'
checks=[]
def ok(name,condition):
    assert condition,name
    checks.append(name)
def run(mode='flatten',text='',paths=(),**options):
    return execute_job(EXE,mode,options,list(paths),text,threading.Event())
def reject(name,fn):
    try:fn()
    except (ValueError,OSError,InterruptedError):checks.append(name);return
    raise AssertionError(name)
def main():
    obj={'name':'きうい','nested':{'a.b':[True,None,2.5]},'empty':{}}
    text=json.dumps(obj,ensure_ascii=False)
    flat=run(text=text);ok('flatten unicode paths',flat['returncode']==0 and b'json.nested["a.b"][0]' in flat['stdout'])
    restored=run('restore',text=flat['stdout'].decode());ok('round trip',json.loads(restored['stdout'])==obj)
    rep=run(text=text,**{'--json':True});ok('JSON stream representation',json.loads(rep['stdout'].splitlines()[0])[0]==[])
    back=run('restore',text=rep['stdout'].decode(),**{'--json':True});ok('representation round trip',json.loads(back['stdout'])==obj)
    stream=run(text='{"a":1}\n{"a":2}\n',**{'--stream':True});ok('JSONL stream',stream['returncode']==0)
    back=run('restore',text=stream['stdout'].decode());ok('stream array restore',json.loads(back['stdout'])==[{'a':1},{'a':2}])
    colored=run(text=text,**{'@color':'colorize'});ok('ANSI raw output',b'\x1b[' in colored['stdout'])
    unsorted=run(text=text,**{'--no-sort':True});ok('no sort semantics',set(unsorted['stdout'].splitlines())==set(flat['stdout'].splitlines()))
    extracted=run('values',text='\n'+flat['stdout'].decode()+'\n');ok('values empty lines removed',extracted['returncode']==0 and 'きうい'.encode() in extracted['stdout'])
    ok('invalid JSON error',run(text='{')['returncode']!=0)
    ok('malformed values rejected',run('values',text='invalid')['returncode']!=0)
    with tempfile.TemporaryDirectory() as td:
        f=Path(td)/'-日本語.json';f.write_text(text,encoding='utf8');before=f.read_bytes()
        ok('file input empty URL/text',run(paths=[str(f)],**{'@url':''})['stdout']==flat['stdout'])
        g=Path(td)/'input.gron';g.write_bytes(flat['stdout'])
        ok('values file stdin workaround',run('values',paths=[str(g)])['stdout']==run('values',text=flat['stdout'].decode())['stdout'])
        ok('original unchanged',f.read_bytes()==before)
        reject('mixed sources',lambda:run(text=text,paths=[str(f)]))
        reject('directory rejected',lambda:run(paths=[td]))
        reject('missing file',lambda:run(paths=[str(f)+'missing']))
    for name,mode,options in [('restore stream','restore',{'--stream':True}),('values JSON','values',{'--json':True}),('restore sorting','restore',{'--no-sort':True}),('values color','values',{'@color':'colorize'}),('insecure no URL','flatten',{'--insecure':True})]:
        reject(name,lambda m=mode,o=options:run(m,text=text,**o))
    reject('no input',lambda:run())
    reject('NUL input',lambda:run(text='{}\0'))
    reject('text bound',lambda:run(text=' '*2097152+'{}'))
    reject('values line bound',lambda:normalize_values(b'x'*65535))
    for url in ('file:///tmp/a','http://localhost:0','http://localhost:99999','http://a b/'):
        reject('bad URL '+url,lambda u=url:build_request('flatten',{'@url':u},[],''))
    cancel=threading.Event();cancel.set();reject('cancel before job',lambda:execute_job(EXE,'flatten',{},[],text,cancel))
    for mode in ('version','help'):
        r=run(mode,text='invalid',paths=['missing'],**{'@url':'invalid','--stream':True});ok(mode+' ignores sources',r['returncode']==0 and bool(r['stdout']))
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/bad':self.send_response(404);self.end_headers();return
            if self.path=='/redirect':self.send_response(302);self.send_header('Location','/json');self.end_headers();return
            if self.path=='/auth' and self.headers.get('Authorization')!='Basic dXNlcjpwYXNz':self.send_response(401);self.end_headers();return
            data=flat['stdout'] if self.path=='/values' else text.encode()
            if self.path=='/big':data=b'x'*2097153
            self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    with http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            ok('URL JSON',run(**{'@url':base+'/json'})['stdout']==flat['stdout'])
            ok('URL redirect',run(**{'@url':base+'/redirect'})['stdout']==flat['stdout'])
            ok('URL values',run('values',**{'@url':base+'/values'})['stdout']==run('values',text=flat['stdout'].decode())['stdout'])
            ok('basic auth',run(**{'@url':base.replace('://','://user:pass@')+'/auth'})['stdout']==flat['stdout'])
            reject('HTTP error',lambda:run(**{'@url':base+'/bad'}))
            reject('URL size bound',lambda:run(**{'@url':base+'/big'}))
        finally:server.shutdown();thread.join()
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import ssl,datetime
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False).sign(key,hashes.SHA256())
    with tempfile.TemporaryDirectory() as td:
        cp=Path(td)/'cert.pem';kp=Path(td)/'key.pem';cp.write_bytes(cert.public_bytes(serialization.Encoding.PEM));kp.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption()))
        with http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
            ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(cp,kp);server.socket=ctx.wrap_socket(server.socket,server_side=True)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url='https://localhost:'+str(server.server_port)+'/json'
            try:
                reject('TLS verification default',lambda:run(**{'@url':url}))
                ok('explicit insecure TLS',run(**{'@url':url,'--insecure':True})['stdout']==flat['stdout'])
            finally:server.shutdown();thread.join()
    target=ROOT/'data/gron/tests.json';target.write_text(json.dumps({'passed':checks},indent=2),encoding='utf8')
    print('PASS',len(checks),'Windows gron checks')
if __name__=='__main__':main()
