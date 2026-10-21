import os,json,sqlite3,uuid,re,base64,hmac,threading,hashlib,secrets,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
DATA=Path(os.getenv('LOCAL_NOTION_DATA_DIR',str(ROOT/'runtime_data'))).resolve()
ASSETS=Path(os.getenv('LOCAL_NOTION_ASSETS_DIR',str(DATA/'assets'))).resolve()
HOST=os.getenv('LOCAL_NOTION_HOST','127.0.0.1')
PORT=int(os.getenv('LOCAL_NOTION_PORT','8765'))
PASSWORD=os.getenv('LOCAL_NOTION_PASSWORD','')
DATA.mkdir(parents=True,exist_ok=True);ASSETS.mkdir(parents=True,exist_ok=True)
DB=DATA/'notion.db';LOCK=threading.RLock();SESSIONS={}
def passhash(value,salt):return hashlib.pbkdf2_hmac('sha256',value.encode(),bytes.fromhex(salt),250000).hex()
def descendants_locked(db,pid):
 seen=set()
 while pid and pid not in seen:
  seen.add(pid);r=db.execute('SELECT parent_id,private_salt,private_hash FROM pages WHERE id=?',(pid,)).fetchone()
  if not r:return []
  if r['private_hash']:yield (pid,r['private_salt'],r['private_hash'])
  pid=r['parent_id']
def cookie_session(handler):
 match=re.search(r'(?:^|;\s*)lnsession=([a-f0-9]{64})(?:;|$)',handler.headers.get('Cookie',''))
 if not match:return None
 token=match.group(1);session=SESSIONS.get(token)
 if session and session['expires']>time.time():return session
 SESSIONS.pop(token,None);return None
def can_read(db,handler,pid):
 if not isinstance(pid,str) or not db.execute('SELECT 1 FROM pages WHERE id=?',(pid,)).fetchone():return False
 s=cookie_session(handler);unlocked=s['pages'] if s else set()
 return all(locked_id in unlocked for locked_id,_,_ in descendants_locked(db,pid))
def connect():
 db=sqlite3.connect(DB,timeout=15);db.row_factory=sqlite3.Row;return db
def now():return datetime.now(timezone.utc).isoformat()
def init():
 with connect() as db:
  db.execute('CREATE TABLE IF NOT EXISTS pages(id TEXT PRIMARY KEY,parent_id TEXT,title TEXT NOT NULL,content TEXT NOT NULL DEFAULT \'\',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)')
  columns={r[1] for r in db.execute('PRAGMA table_info(pages)')}
  if 'private_salt' not in columns:db.execute('ALTER TABLE pages ADD COLUMN private_salt TEXT')
  if 'private_hash' not in columns:db.execute('ALTER TABLE pages ADD COLUMN private_hash TEXT')
  db.execute('CREATE TABLE IF NOT EXISTS images(name TEXT PRIMARY KEY,page_id TEXT NOT NULL)')
  if not db.execute('SELECT 1 FROM pages LIMIT 1').fetchone():
   t=now();db.execute('INSERT INTO pages(id,parent_id,title,content,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),None,'시작하기','# Local Notion\n\n왼쪽에서 페이지를 추가하세요.',1,t,t))
def valid_parent(db,parent,current=None):
 if parent is None:return True
 if not isinstance(parent,str):return False
 seen={current} if current else set()
 while parent is not None:
  if parent in seen:return False
  seen.add(parent);r=db.execute('SELECT parent_id FROM pages WHERE id=?',(parent,)).fetchone()
  if not r:return False
  parent=r['parent_id']
 return True
class Handler(BaseHTTPRequestHandler):
 def send(self,status,data,mime,headers=None):
  self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
  self.send_header('X-Content-Type-Options','nosniff')
  self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'")
  self.send_header('Cache-Control','no-store')
  self.send_header('Referrer-Policy','no-referrer')
  for k,v in (headers or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(data)
 def result(self,status,obj):self.send(status,json.dumps(obj,ensure_ascii=False).encode(),'application/json; charset=utf-8')
 def guard(self,write=False):
  if PASSWORD:
   a=self.headers.get('Authorization','')
   try: decoded=base64.b64decode(a[6:],validate=True).decode() if a.startswith('Basic ') else ''
   except(ValueError,UnicodeError):decoded=''
   u,sep,p=decoded.partition(':')
   authorized=bool(sep) and hmac.compare_digest(u,'staff') and hmac.compare_digest(p,PASSWORD)
  else:authorized=self.client_address[0] in ('127.0.0.1','::1')
  if not authorized:
   self.send(401,b'Authentication required','text/plain',{'WWW-Authenticate':'Basic realm="Local Notion"'});return False
  if write:
   origin=self.headers.get('Origin')
   if origin and urlparse(origin).netloc!=self.headers.get('Host',''):
    self.result(403,{'error':'Invalid Origin'});return False
  return True
 def body(self):
  try:
   n=int(self.headers.get('Content-Length','-1'))
   if n<0 or n>2000000:raise ValueError()
   return json.loads(self.rfile.read(n))
  except(ValueError,json.JSONDecodeError):return None
 def do_GET(self):
  if not self.guard():return
  path=urlparse(self.path).path
  if path=='/':self.send(200,(ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
  elif path=='/api/pages':
   with connect() as db:
    rows=[]
    for p in db.execute('SELECT * FROM pages ORDER BY created_at'):
     d=dict(p);locked=not can_read(db,self,d['id']);d['locked']=locked;d['private']=bool(d['private_hash']);d.pop('private_hash');d.pop('private_salt')
     if locked:d['title']='🔒 개인 페이지';d['content']=''
     rows.append(d)
    self.result(200,{'pages':rows})
  elif path.startswith('/assets/'):
   name=path.rsplit('/',1)[-1]
   if not re.fullmatch(r'[0-9a-f]{32}\.(png|jpg|gif|webp)',name) or not (ASSETS/name).is_file():return self.result(404,{'error':'Not found'})
   with connect() as db:
    owner=db.execute('SELECT page_id FROM images WHERE name=?',(name,)).fetchone()
    if not owner or not can_read(db,self,owner['page_id']):return self.result(404,{'error':'Not found'})
   mime={'png':'image/png','jpg':'image/jpeg','gif':'image/gif','webp':'image/webp'}[name.rsplit('.',1)[-1]]
   self.send(200,(ASSETS/name).read_bytes(),mime)
  else:self.result(404,{'error':'Not found'})
 def do_POST(self):
  if not self.guard(True):return
  path=urlparse(self.path).path
  if path=='/api/upload':return self.upload()
  body=self.body()
  if not isinstance(body,dict):return self.result(400,{'error':'Invalid JSON'})
  with LOCK,connect() as db:
   if path=='/api/unlock':
    pid=body.get('id');pw=body.get('password')
    if not isinstance(pid,str) or not isinstance(pw,str):return self.result(400,{'error':'Invalid request'})
    row=db.execute('SELECT private_salt,private_hash FROM pages WHERE id=?',(pid,)).fetchone()
    if not row or not row['private_hash']:return self.result(404,{'error':'Locked page not found'})
    if not hmac.compare_digest(passhash(pw,row['private_salt']),row['private_hash']):return self.result(403,{'error':'암호가 틀렸습니다'})
    session=cookie_session(self);token=secrets.token_hex(32) if not session else session['token']
    if not session:session={'token':token,'pages':set(),'expires':time.time()+3600};SESSIONS[token]=session
    session['pages'].add(pid);session['expires']=time.time()+3600
    self.send(200,b'{"ok":true}','application/json',{'Set-Cookie':f'lnsession={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600'})
    return
   if path=='/api/privacy':
    pid=body.get('id');new_pw=body.get('password');old_pw=body.get('old_password')
    row=db.execute('SELECT private_salt,private_hash FROM pages WHERE id=?',(pid,)).fetchone() if isinstance(pid,str) else None
    if not row:return self.result(404,{'error':'Page not found'})
    if row['private_hash'] and (not isinstance(old_pw,str) or not hmac.compare_digest(passhash(old_pw,row['private_salt']),row['private_hash'])):return self.result(403,{'error':'현재 암호가 필요합니다'})
    if new_pw is not None and (not isinstance(new_pw,str) or len(new_pw)<8 or len(new_pw)>256):return self.result(400,{'error':'암호는 8~256자여야 합니다'})
    salt=secrets.token_hex(16) if new_pw else None;hashed=passhash(new_pw,salt) if new_pw else None
    db.execute('UPDATE pages SET private_salt=?,private_hash=? WHERE id=?',(salt,hashed,pid));db.commit()
    return self.result(200,{'ok':True})
   if path=='/api/pages':
    title=body.get('title','새 페이지');parent=body.get('parent_id')
    if not isinstance(title,str) or not 1<=len(title.strip())<=200 or not valid_parent(db,parent) or (parent and not can_read(db,self,parent)):return self.result(400,{'error':'Invalid title or parent'})
    pid=str(uuid.uuid4());t=now();db.execute('INSERT INTO pages VALUES(?,?,?,?,?,?,?)',(pid,parent,title.strip(),'',1,t,t));db.commit()
    return self.result(201,{'id':pid})
   if path=='/api/save':
    pid,title,content,ver=(body.get(k) for k in ('id','title','content','version'));parent=body.get('parent_id')
    if not isinstance(pid,str) or not isinstance(title,str) or not 1<=len(title.strip())<=200 or not isinstance(content,str) or len(content)>1000000 or type(ver)!=int or not valid_parent(db,parent,pid) or not can_read(db,self,pid) or (parent and not can_read(db,self,parent)):return self.result(403,{'error':'Access denied'})
    r=db.execute('UPDATE pages SET title=?,content=?,parent_id=?,version=version+1,updated_at=? WHERE id=? AND version=?',(title.strip(),content,parent,now(),pid,ver));db.commit()
    return self.result(200,{'version':ver+1}) if r.rowcount else self.result(409,{'error':'다른 사용자가 수정했습니다. 다시 불러오세요.'})
   if path=='/api/delete':
    pid=body.get('id')
    if not isinstance(pid,str) or not can_read(db,self,pid):return self.result(403,{'error':'Access denied'})
    rows=[dict(r) for r in db.execute('SELECT id,parent_id FROM pages')];ids={pid}
    while True:
     extra={r['id'] for r in rows if r['parent_id'] in ids}
     if extra.issubset(ids):break
     ids|=extra
    for id in ids:db.execute('DELETE FROM pages WHERE id=?',(id,))
    db.commit();return self.result(200,{'deleted':len(ids)})
  self.result(404,{'error':'Not found'})
 def upload(self):
  try:n=int(self.headers.get('Content-Length','0'))
  except ValueError:n=0
  if not 0<n<=20*1024*1024:return self.result(413,{'error':'Max 20MB'})
  pid=self.headers.get('X-Page-ID','')
  with connect() as db:
   if not db.execute('SELECT 1 FROM pages WHERE id=?',(pid,)).fetchone() or not can_read(db,self,pid):return self.result(403,{'error':'Access denied'})
  mime=self.headers.get('Content-Type','').split(';')[0]
  kinds={'image/png':('png',b'\x89PNG\r\n\x1a\n'),'image/jpeg':('jpg',b'\xff\xd8\xff'),'image/gif':('gif',b'GIF8'),'image/webp':('webp',b'RIFF')}
  if mime not in kinds:return self.result(415,{'error':'이미지 파일만 지원합니다'})
  ext,header=kinds[mime];data=self.rfile.read(n)
  if len(data)!=n or not data.startswith(header) or (ext=='webp' and data[8:12]!=b'WEBP'):return self.result(400,{'error':'Invalid image'})
  filename=uuid.uuid4().hex+'.'+ext;(ASSETS/filename).write_bytes(data)
  with LOCK,connect() as db:db.execute('INSERT INTO images(name,page_id) VALUES(?,?)',(filename,pid));db.commit()
  self.result(201,{'url':'/assets/'+filename})
if __name__=='__main__':
 if HOST not in ('localhost','127.0.0.1','::1') and not PASSWORD:raise SystemExit('LOCAL_NOTION_PASSWORD required for network access')
 init();print('Local Notion:',HOST,PORT,flush=True)
 ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
