"""Local Notion: per-PC localhost server, shared file documents, exclusive edit locks."""
import os,json,uuid,socket,threading,time,hashlib,base64,re,secrets,shutil,zipfile,io
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,unquote
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('LOCAL_NOTION_DATA_DIR',str(ROOT/'shared_data'))).resolve()
PAGES=DATA/'pages';LOCKS=DATA/'locks';IMAGES=DATA/'images';ATTACHMENTS=DATA/'attachments';HISTORY=DATA/'history';TRASH=DATA/'trash';BACKUPS=DATA/'backups';VAULT=DATA/'vault'
for p in (PAGES,LOCKS,IMAGES,ATTACHMENTS,HISTORY,TRASH,BACKUPS,VAULT):p.mkdir(parents=True,exist_ok=True)
USER=os.environ.get('USERNAME') or os.environ.get('USER') or 'user'
HOSTNAME=socket.gethostname();OWNER=HOSTNAME+'/'+USER
PORT=int(os.environ.get('LOCAL_NOTION_PORT','8765'))
LOCAL_TOKEN=secrets.token_hex(24)
PAGE_ID=re.compile(r'^[0-9a-f]{32}$')
IMAGE_ID=re.compile(r'^[0-9a-f]{32}\.(png|jpg|gif|webp)$')
MUTEX=threading.RLock()
def utc():return datetime.now(timezone.utc).isoformat()
def file_for(pid):return PAGES/(pid+'.json')
def lock_for(pid):return LOCKS/pid
def historical(pid,obj):
 directory=HISTORY/pid;directory.mkdir(exist_ok=True)
 out=directory/('%08d.json'%obj['version'])
 if not out.exists():atomic_json(out,obj)
def all_pages():
 return [r for file in PAGES.glob('*.json') if (r:=read_page(file.stem))]
def backup():
 name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.zip'
 target=BACKUPS/name;tmp=target.with_suffix('.tmp')
 try:
  with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED) as archive:
   for folder in (PAGES,HISTORY,TRASH,IMAGES,ATTACHMENTS,VAULT):
    for path in folder.rglob('*'):
     if path.is_file():archive.write(path,path.relative_to(DATA))
  os.replace(tmp,target)
 finally:tmp.unlink(missing_ok=True)
 return name
def daily_backup():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%d')
 marker=BACKUPS/('daily-'+stamp+'.lock')
 try:marker.mkdir()
 except FileExistsError:return
 try:backup()
 except Exception:
  try:marker.rmdir()
  except OSError:pass
  raise
def read_page(pid):
 if not isinstance(pid,str) or not PAGE_ID.fullmatch(pid):return None
 try:return json.loads(file_for(pid).read_text(encoding='utf-8'))
 except(FileNotFoundError,ValueError):return None
def atomic_json(path,obj):
 tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
 try:
  with open(tmp,'x',encoding='utf-8') as f:
   json.dump(obj,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:tmp.unlink(missing_ok=True)
def lock_info(pid):
 try:return json.loads((lock_for(pid)/'owner.json').read_text(encoding='utf-8'))
 except(FileNotFoundError,ValueError):return None
def active_lock(pid):
 d=lock_for(pid)
 if not d.exists():return None
 return lock_info(pid) or {'owner':'잠금 정보 확인 불가','since':'','token':None}
def validate_parent(pid,parent):
 if parent is None:return True
 seen={pid}
 while parent:
  if parent in seen:return False
  seen.add(parent);p=read_page(parent)
  if not p:return False
  parent=p.get('parent_id')
 return True
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,status,obj,headers=None):
  data=json.dumps(obj,ensure_ascii=False).encode()
  self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)))
  self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
  for k,v in (headers or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(data)
 def auth(self):
  if self.headers.get('X-Local-Token')!=LOCAL_TOKEN:return self.reply(403,{'error':'Local session required'})
  return True
 def body(self):
  try:
   n=int(self.headers.get('Content-Length','0'))
   if n<1 or n>2000000:return None
   return json.loads(self.rfile.read(n))
  except(ValueError,UnicodeError):return None
 def do_GET(self):
  p=urlparse(self.path).path
  if p in ('/','/legacy'):
   body=(ROOT/('wysiwyg.html' if p=='/' else 'local_index.html')).read_bytes()
   self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)))
   self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'")
   self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body);return
  if p=='/api/session':return self.reply(200,{'token':LOCAL_TOKEN,'owner':OWNER})
  if p=='/wysiwyg':
   data=(ROOT/'wysiwyg.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'");self.end_headers();self.wfile.write(data);return
  if p=='/vault':
   data=(ROOT/'vault.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'");self.end_headers();self.wfile.write(data);return
  if p.startswith('/images/') or p.startswith('/attachments/'):
   site=self.headers.get('Sec-Fetch-Site','')
   if site not in ('same-origin','none',''):return self.reply(403,{'error':'Cross-site image request rejected'})
  elif not self.auth():return
  if p=='/api/vault/list':return self.reply(200,{'items':[{'id':x.stem} for x in VAULT.glob('*.json') if PAGE_ID.fullmatch(x.stem)]})
  if p=='/api/history':
   from urllib.parse import parse_qs
   pid=parse_qs(urlparse(self.path).query).get('id',[''])[0]
   if not PAGE_ID.fullmatch(pid):return self.reply(400,{'error':'Invalid id'})
   files=sorted((HISTORY/pid).glob('*.json'),reverse=True) if (HISTORY/pid).exists() else []
   return self.reply(200,{'versions':[{'version':int(x.stem),'updated_at':json.loads(x.read_text(encoding='utf-8')).get('updated_at')} for x in files]})
  if p=='/api/trash':return self.reply(200,{'pages':[json.loads(x.read_text(encoding='utf-8')) for x in TRASH.glob('*.json')]})
  if p=='/api/pages':
   pages=[]
   for path in PAGES.glob('*.json'):
    item=read_page(path.stem)
    if item and not item.get('deleted'):pages.append({**item,'lock':active_lock(item['id']) and {k:v for k,v in active_lock(item['id']).items() if k!='token'}})
   return self.reply(200,{'pages':sorted(pages,key=lambda r:r.get('created_at',''))})
  if p.startswith('/attachments/'):
   name=unquote(p.split('/')[-1]);valid=re.fullmatch(r'[0-9a-f]{32}\.(pdf|docx|xlsx|pptx|csv)',name)
   if not valid:return self.reply(404,{'error':'Not found'})
   path=ATTACHMENTS/name
   if not path.is_file():return self.reply(404,{'error':'Not found'})
   data=path.read_bytes();self.send_response(200);self.send_header('Content-Type','application/octet-stream');self.send_header('Content-Disposition','attachment; filename="'+name+'"');self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data);return
  if p.startswith('/images/'):
   name=unquote(p.split('/')[-1])
   if not IMAGE_ID.fullmatch(name):return self.reply(404,{'error':'Not found'})
   path=IMAGES/name
   if not path.is_file():return self.reply(404,{'error':'Not found'})
   mime={'png':'image/png','jpg':'image/jpeg','gif':'image/gif','webp':'image/webp'}[name.rsplit('.',1)[1]]
   data=path.read_bytes();self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)));self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data);return
  return self.reply(404,{'error':'Not found'})
 def do_POST(self):
  if not self.auth():return
  p=urlparse(self.path).path
  if p=='/api/image':return self.image_upload()
  if p=='/api/attachment':return self.attachment_upload()
  body=self.body()
  if not isinstance(body,dict):return self.reply(400,{'error':'Invalid JSON'})
  with MUTEX:
   if p=='/api/vault/create':
    pid=uuid.uuid4().hex
    return self.reply(201,{'id':pid})
   if p=='/api/vault/read':
    pid=body.get('id')
    if not isinstance(pid,str) or not PAGE_ID.fullmatch(pid):return self.reply(400,{'error':'Invalid vault id'})
    file=VAULT/(pid+'.json')
    if not file.is_file():return self.reply(404,{'error':'Not found'})
    return self.reply(200,json.loads(file.read_text(encoding='utf-8')))
   if p=='/api/vault/save':
    pid=body.get('id');salt=body.get('salt');iv=body.get('iv');ciphertext=body.get('ciphertext');locktoken=body.get('lock_token')
    if not isinstance(pid,str) or not PAGE_ID.fullmatch(pid):return self.reply(400,{'error':'Invalid id'})
    if not all(isinstance(v,str) for v in (salt,iv,ciphertext)) or len(ciphertext)>1600000:return self.reply(400,{'error':'Invalid encrypted payload'})
    if not re.fullmatch(r'[A-Za-z0-9+/=]{20,100}',salt) or not re.fullmatch(r'[A-Za-z0-9+/=]{12,100}',iv) or not re.fullmatch(r'[A-Za-z0-9+/=]{20,1600000}',ciphertext):return self.reply(400,{'error':'Invalid encoding'})
    lock=lock_info(pid)
    if not lock or not secrets.compare_digest(str(locktoken),str(lock.get('token'))):return self.reply(423,{'error':'Vault lock is required'})
    target=VAULT/(pid+'.json');expected=body.get('version')
    if target.exists():
     current=json.loads(target.read_text(encoding='utf-8'))
     if current['version']!=expected:return self.reply(409,{'error':'Encrypted page changed'})
     version=current['version']+1
    else:
     if expected!=0:return self.reply(409,{'error':'Invalid initial version'})
     version=1
    atomic_json(target,{'salt':salt,'iv':iv,'ciphertext':ciphertext,'version':version})
    return self.reply(200,{'version':version})
   if p=='/api/backup':return self.reply(200,{'filename':backup()})
   if p=='/api/restore_trash':
    pid=body.get('id')
    if not isinstance(pid,str) or not PAGE_ID.fullmatch(pid):return self.reply(400,{'error':'Invalid id'})
    t=TRASH/(pid+'.json')
    if not t.exists() or file_for(pid).exists():return self.reply(409,{'error':'Cannot restore'})
    os.replace(t,file_for(pid));return self.reply(200,{'ok':True})
   if p=='/api/create':
    parent=body.get('parent_id')
    title=body.get('title','새 페이지')
    if not isinstance(title,str) or not 1<=len(title.strip())<=200 or not validate_parent('new',parent):return self.reply(400,{'error':'Invalid page'})
    pid=uuid.uuid4().hex;t=utc();obj={'id':pid,'title':title.strip(),'parent_id':parent,'content':'','version':1,'created_at':t,'updated_at':t,'author':OWNER}
    # Exclusive creation is safe because UUIDs are unique.
    atomic_json(file_for(pid),obj);return self.reply(201,{'id':pid})
   pid=body.get('id')
   if not isinstance(pid,str) or not PAGE_ID.fullmatch(pid):return self.reply(400,{'error':'Invalid id'})
   if p=='/api/lock':
    if not read_page(pid) and not (VAULT/(pid+'.json')).exists() and body.get('vault')!=True:return self.reply(404,{'error':'Not found'})
    folder=lock_for(pid);token=secrets.token_hex(24)
    try:folder.mkdir()
    except FileExistsError:return self.reply(423,{'error':'다른 직원이 편집 중입니다.','lock':active_lock(pid)})
    data={'owner':OWNER,'since':utc(),'token':token}
    try:atomic_json(folder/'owner.json',data)
    except Exception:folder.rmdir();raise
    return self.reply(200,{'lock_token':token})
   if p=='/api/unlock':
    lock=lock_info(pid)
    if not lock or not secrets.compare_digest(str(body.get('lock_token','')),str(lock.get('token','x'))):return self.reply(423,{'error':'현재 편집권이 없습니다'})
    (lock_for(pid)/'owner.json').unlink();lock_for(pid).rmdir();return self.reply(200,{'ok':True})
   if p=='/api/save':
    lock=lock_info(pid)
    if not lock or not secrets.compare_digest(str(body.get('lock_token','')),str(lock.get('token','x'))):return self.reply(423,{'error':'편집 잠금이 없거나 다른 직원이 소유합니다'})
    old=read_page(pid)
    if not old:return self.reply(404,{'error':'Not found'})
    if type(body.get('version')) is not int or old['version']!=body['version']:return self.reply(409,{'error':'다른 버전입니다. 새로고침하세요'})
    title,content,parent=body.get('title'),body.get('content'),body.get('parent_id')
    if not isinstance(title,str) or not 1<=len(title.strip())<=200 or not isinstance(content,str) or len(content)>1000000 or not validate_parent(pid,parent):return self.reply(400,{'error':'Invalid content'})
    # Serialize saves for each page with its lock; shared filesystem must implement atomic mkdir/rename.
    current=read_page(pid)
    if current['version']!=old['version']:return self.reply(409,{'error':'저장 충돌'})
    old.update(title=title.strip(),content=content,parent_id=parent,version=old['version']+1,updated_at=utc(),author=OWNER)
    historical(pid,current);atomic_json(file_for(pid),old);return self.reply(200,{'version':old['version']})
   if p=='/api/restore_version':
    lock=lock_info(pid)
    if not lock or not secrets.compare_digest(str(body.get('lock_token','')),str(lock.get('token','x'))):return self.reply(423,{'error':'편집 잠금이 필요합니다'})
    version=body.get('version')
    if type(version)!=int or version<1:return self.reply(400,{'error':'Invalid version'})
    path=HISTORY/pid/('%08d.json'%version)
    if not path.exists():return self.reply(404,{'error':'Version not found'})
    old=read_page(pid);restored=json.loads(path.read_text(encoding='utf-8'))
    historical(pid,old);restored['version']=old['version']+1;restored['updated_at']=utc();restored['author']=OWNER
    atomic_json(file_for(pid),restored);return self.reply(200,{'version':restored['version']})
   if p=='/api/delete':
    lock=lock_info(pid)
    if not lock or not secrets.compare_digest(str(body.get('lock_token','')),str(lock.get('token','x'))):return self.reply(423,{'error':'편집 잠금이 필요합니다'})
    if any((r:=read_page(path.stem)) and r.get('parent_id')==pid for path in PAGES.glob('*.json')):return self.reply(409,{'error':'하위 페이지를 먼저 삭제하세요'})
    historical(pid,read_page(pid));os.replace(file_for(pid),TRASH/(pid+'.json'));(lock_for(pid)/'owner.json').unlink(missing_ok=True);lock_for(pid).rmdir()
    return self.reply(200,{'ok':True})
  return self.reply(404,{'error':'Not found'})
 def attachment_upload(self):
  try:n=int(self.headers.get('Content-Length','0'))
  except ValueError:n=0
  if n<1 or n>20*1024*1024:return self.reply(413,{'error':'20MB 이하만 허용'})
  ext=self.headers.get('X-File-Extension','').lower()
  if ext not in ('pdf','docx','xlsx','pptx','csv'):return self.reply(415,{'error':'Unsupported extension'})
  data=self.rfile.read(n)
  if len(data)!=n:return self.reply(400,{'error':'Incomplete file'})
  if ext=='pdf' and not data.startswith(b'%PDF-'):return self.reply(400,{'error':'Invalid PDF'})
  if ext in ('docx','xlsx','pptx') and not data.startswith(b'PK\\x03\\x04'):return self.reply(400,{'error':'Invalid Office file'})
  name=uuid.uuid4().hex+'.'+ext;path=ATTACHMENTS/name
  with open(path,'xb') as out:out.write(data)
  return self.reply(201,{'url':'/attachments/'+name})
 def image_upload(self):
  try:n=int(self.headers.get('Content-Length','0'))
  except ValueError:n=0
  if not 0<n<=20*1024*1024:return self.reply(413,{'error':'20MB 이하만 가능합니다'})
  mime=self.headers.get('Content-Type','')
  signatures={'image/png':('png',b'\x89PNG\r\n\x1a\n'),'image/jpeg':('jpg',b'\xff\xd8\xff'),'image/gif':('gif',b'GIF8'),'image/webp':('webp',b'RIFF')}
  if mime not in signatures:return self.reply(415,{'error':'이미지 형식만 지원'})
  ext,sig=signatures[mime];data=self.rfile.read(n)
  if len(data)!=n or not data.startswith(sig) or (ext=='webp' and data[8:12]!=b'WEBP'):return self.reply(400,{'error':'이미지 형식 오류'})
  name=uuid.uuid4().hex+'.'+ext;(IMAGES/name).write_bytes(data);return self.reply(201,{'url':'/images/'+name})
if __name__=='__main__':
 try:daily_backup()
 except Exception as error:print('Backup warning:',error)
 print('Shared folder:',DATA)
 print('Local Notion: http://127.0.0.1:'+str(PORT))
 ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
