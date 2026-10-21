import os,json,sqlite3,uuid,re,base64,hmac,threading
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
DB=DATA/'notion.db';LOCK=threading.RLock()
def connect():
 db=sqlite3.connect(DB,timeout=15);db.row_factory=sqlite3.Row;return db
def now():return datetime.now(timezone.utc).isoformat()
def init():
 with connect() as db:
  db.execute('CREATE TABLE IF NOT EXISTS pages(id TEXT PRIMARY KEY,parent_id TEXT,title TEXT NOT NULL,content TEXT NOT NULL DEFAULT \'\',version INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)')
  if not db.execute('SELECT 1 FROM pages LIMIT 1').fetchone():
   t=now();db.execute('INSERT INTO pages VALUES(?,?,?,?,?,?,?)',(str(uuid.uuid4()),None,'시작하기','# Local Notion\n\n왼쪽에서 페이지를 추가하세요.',1,t,t))
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
   with connect() as db:self.result(200,{'pages':[dict(r) for r in db.execute('SELECT * FROM pages ORDER BY created_at')]})
  elif path.startswith('/assets/'):
   name=path.rsplit('/',1)[-1]
   if not re.fullmatch(r'[0-9a-f]{32}\.(png|jpg|gif|webp)',name) or not (ASSETS/name).is_file():return self.result(404,{'error':'Not found'})
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
   if path=='/api/pages':
    title=body.get('title','새 페이지');parent=body.get('parent_id')
    if not isinstance(title,str) or not 1<=len(title.strip())<=200 or not valid_parent(db,parent):return self.result(400,{'error':'Invalid title or parent'})
    pid=str(uuid.uuid4());t=now();db.execute('INSERT INTO pages VALUES(?,?,?,?,?,?,?)',(pid,parent,title.strip(),'',1,t,t));db.commit()
    return self.result(201,{'id':pid})
   if path=='/api/save':
    pid,title,content,ver=(body.get(k) for k in ('id','title','content','version'));parent=body.get('parent_id')
    if not isinstance(pid,str) or not isinstance(title,str) or not 1<=len(title.strip())<=200 or not isinstance(content,str) or len(content)>1000000 or type(ver)!=int or not valid_parent(db,parent,pid):return self.result(400,{'error':'Invalid page'})
    r=db.execute('UPDATE pages SET title=?,content=?,parent_id=?,version=version+1,updated_at=? WHERE id=? AND version=?',(title.strip(),content,parent,now(),pid,ver));db.commit()
    return self.result(200,{'version':ver+1}) if r.rowcount else self.result(409,{'error':'다른 사용자가 수정했습니다. 다시 불러오세요.'})
   if path=='/api/delete':
    pid=body.get('id')
    if not isinstance(pid,str):return self.result(400,{'error':'Invalid id'})
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
  mime=self.headers.get('Content-Type','').split(';')[0]
  kinds={'image/png':('png',b'\x89PNG\r\n\x1a\n'),'image/jpeg':('jpg',b'\xff\xd8\xff'),'image/gif':('gif',b'GIF8'),'image/webp':('webp',b'RIFF')}
  if mime not in kinds:return self.result(415,{'error':'이미지 파일만 지원합니다'})
  ext,header=kinds[mime];data=self.rfile.read(n)
  if len(data)!=n or not data.startswith(header) or (ext=='webp' and data[8:12]!=b'WEBP'):return self.result(400,{'error':'Invalid image'})
  filename=uuid.uuid4().hex+'.'+ext;(ASSETS/filename).write_bytes(data);self.result(201,{'url':'/assets/'+filename})
if __name__=='__main__':
 if HOST not in ('localhost','127.0.0.1','::1') and not PASSWORD:raise SystemExit('LOCAL_NOTION_PASSWORD required for network access')
 init();print('Local Notion:',HOST,PORT,flush=True)
 ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
