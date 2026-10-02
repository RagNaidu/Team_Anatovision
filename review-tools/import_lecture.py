"""Import one original Word lecture. Importing does not perform factual review."""
import argparse,base64,json,shutil,zipfile
from pathlib import Path
from lxml import etree as E
ROOT = Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('document',type=Path);p.add_argument('--number',type=int,required=True);p.add_argument('--title',required=True);p.add_argument('--version',default='1.0');p.add_argument('--replace',action='store_true')
a=p.parse_args();assert 1<=a.number<=99
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'};id=f'lecture-{a.number:02d}'
lectures=json.loads((ROOT/'data/lectures.json').read_text());existing=any(l['id']==id for l in lectures)
if existing and not a.replace:p.error('Lecture already exists. Use --replace only after archiving and re-reviewing affected findings.')
findings=json.loads((ROOT/'data/findings.json').read_text())
if existing and any(f['lectureId']==id for f in findings):p.error('Archive and remove this lecture\'s findings first: paragraph anchors become stale when originals change.')
with zipfile.ZipFile(a.document) as z:parts={n:z.read(n) for n in z.namelist()}
doc=E.fromstring(parts['word/document.xml']);styles=E.fromstring(parts['word/styles.xml'])
names={s.get('{'+ns['w']+'}styleId'):s.find('w:name',ns).get('{'+ns['w']+'}val') for s in styles.findall('w:style',ns) if s.find('w:name',ns) is not None}
paragraphs=[]
for i,paragraph in enumerate(doc.xpath('//w:p',namespaces=ns)):
 text=''.join(paragraph.xpath('.//w:t/text()',namespaces=ns))
 if not text.strip():continue
 styleid=paragraph.xpath('w:pPr/w:pStyle/@w:val',namespaces=ns);style=names.get(styleid[0],styleid[0]) if styleid else 'Normal'
 if style.lower().startswith('heading '):style=style.title()
 paragraphs.append({'index':i,'text':text,'style':style})
if doc.xpath('//w:tbl',namespaces=ns):p.error('Tables require a reviewed structured import; this importer does not flatten them silently.')
lecture={'id':id,'number':f'{a.number:02d}','title':a.title,'filename':a.document.name,'paragraphs':paragraphs,'tables':[],'images':sum(n.startswith('word/media/') for n in parts),'version':a.version,'sections':sum(x['style'].startswith('Heading') for x in paragraphs)}
lectures=[l for l in lectures if l['id']!=id]+[lecture];lectures.sort(key=lambda l:l['number'])
(ROOT/'data/lectures.json').write_text(json.dumps(lectures,indent=2,ensure_ascii=False)+'\n')
out=ROOT/'public/documents';shutil.copy2(a.document,out/f'{id}.docx')
(out/f'{id}-parts.json').write_text(json.dumps({n:base64.b64encode(v).decode() for n,v in parts.items()}))
print('Imported',id,'with',len(paragraphs),'paragraphs. Factual review and faculty approval are still required. Update UI totals if adding lectures beyond the original ten.')
