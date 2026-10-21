"""Import a user-authorized Notion HTML export folder into Local Notion.
Usage: python import_notion_html.py "C:\\path\\to\\export-folder"
Only reads local HTML files. Does NOT connect to Notion or bypass export permissions.
"""
import sys,re,uuid,json,os,shutil,html
from pathlib import Path
from html.parser import HTMLParser
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('LOCAL_NOTION_DATA_DIR',str(ROOT/'shared_data'))).resolve()
PAGES=DATA/'pages';IMAGES=DATA/'images'
class Extract(HTMLParser):
 def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.images=[];self.tagstack=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs);self.tagstack.append(tag)
  if tag in ('p','div','li','h1','h2','h3','blockquote'):self.parts.append('\n')
  if tag in ('h1','h2','h3'):self.parts.append('#'*int(tag[1])+' ')
  if tag=='li':self.parts.append('- ')
  if tag=='img' and a.get('src'):self.images.append((a['src'],a.get('alt','이미지')));self.parts.append('\n@@LOCAL_IMAGE_'+str(len(self.images)-1)+'@@\n')
 def handle_endtag(self,tag):
  if tag in ('p','div','li','h1','h2','h3','blockquote'):self.parts.append('\n')
  if tag in self.tagstack:self.tagstack.remove(tag)
 def handle_data(self,data):
  if not any(tag in ('script','style') for tag in self.tagstack):self.parts.append(data)
def main():
 if len(sys.argv)!=2:raise SystemExit('Usage: python import_notion_html.py EXPORT_DIRECTORY')
 base=Path(sys.argv[1]).resolve()
 if not base.is_dir():raise SystemExit('The export directory does not exist.')
 htmlfiles=list(base.rglob('*.html'))
 if len(htmlfiles)>1000:raise SystemExit('More than 1000 pages: split the import.')
 if not htmlfiles:raise SystemExit('No HTML files found.')
 PAGES.mkdir(parents=True,exist_ok=True);IMAGES.mkdir(parents=True,exist_ok=True)
 result=[]
 for source in htmlfiles:
  if source.stat().st_size>5*1024*1024:print('SKIP oversized HTML',source);continue
  reader=Extract();reader.feed(source.read_text(encoding='utf-8-sig',errors='replace'))
  body=''.join(reader.parts)
  for i,(relative,alt) in enumerate(reader.images):
   relative=relative.split('?')[0].split('#')[0]
   from urllib.parse import unquote,urlparse
   uri=urlparse(relative)
   if uri.scheme or uri.netloc or relative.startswith(('/', '\\\\')):body=body.replace('@@LOCAL_IMAGE_'+str(i)+'@@','[외부 이미지 링크 - 검토 필요]');continue
   path=(source.parent/unquote(uri.path)).resolve()
   if not path.is_relative_to(base) or not path.is_file() or path.stat().st_size>20*1024*1024:body=body.replace('@@LOCAL_IMAGE_'+str(i)+'@@','[이미지 누락]');continue
   ext=path.suffix.lower()
   if ext not in ('.png','.jpg','.jpeg','.gif','.webp'):body=body.replace('@@LOCAL_IMAGE_'+str(i)+'@@','[지원되지 않는 이미지]');continue
   suffix='.jpg' if ext=='.jpeg' else ext
   new=uuid.uuid4().hex+suffix;shutil.copyfile(path,IMAGES/new)
   body=body.replace('@@LOCAL_IMAGE_'+str(i)+'@@','!['+alt.replace('[','').replace(']','').replace('(','').replace(')','')+'](/images/'+new+')')
  title=html.unescape(source.stem)[:200] or 'Imported page'
  now=datetime.now(timezone.utc).isoformat();pid=uuid.uuid4().hex
  page={'id':pid,'title':title,'parent_id':None,'content':body.strip(),'version':1,'created_at':now,'updated_at':now,'author':'notion-import'}
  target=PAGES/(pid+'.json')
  with target.open('x',encoding='utf-8') as f:json.dump(page,f,ensure_ascii=False)
  result.append(title)
 print('Imported:',len(result),'pages. Verify text, hierarchy and images before relying on the content.')
if __name__=='__main__':main()
