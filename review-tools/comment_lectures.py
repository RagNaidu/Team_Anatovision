import json,zipfile,shutil
from pathlib import Path
from lxml import etree as E
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'review-output';OUT.mkdir(exist_ok=True)
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main';R='http://schemas.openxmlformats.org/package/2006/relationships';CT='http://schemas.openxmlformats.org/package/2006/content-types'
def node(tag,**attrs):
 e=E.Element('{'+W+'}'+tag)
 for k,v in attrs.items():e.set('{'+W+'}'+k,str(v))
 return e
def xml(d):return E.tostring(d,xml_declaration=True,encoding='UTF-8',standalone=True)
lectures=json.loads((ROOT/'data/lectures.json').read_text());findings=json.loads((ROOT/'data/findings.json').read_text())
index=['LECTURE NOTES WITH COMMENTS','AI review completed 1 October 2026','All ten lectures were read. Highlights and Word comments identify possible factual errors, misleading mechanisms and material omissions. These are proposals for faculty review, not certified corrections. No original wording has been replaced.','Workflow: upload these files to Lecture Notes (With Comments). Professor reviews suggestions, edits accepted changes, and places clean approved copies in Lecture Notes (Revised). Only those copies should feed the student AI.','Open in Microsoft Word and use Review > Show Comments. Yellow highlight marks the original paragraph.']
for l in lectures:
 src=ROOT/'public/documents'/f"{l['id']}.docx"
 with zipfile.ZipFile(src) as z:parts={n:z.read(n) for n in z.namelist()}
 d=E.fromstring(parts['word/document.xml']);ps=d.findall('.//{'+W+'}p');before=[''.join(p.itertext()) for p in ps]
 comments=E.fromstring(parts.get('word/comments.xml',f'<w:comments xmlns:w="{W}"/>'.encode()))
 nextid=max([int(c.get('{'+W+'}id')) for c in comments]+[-1])+1
 fs=[f for f in findings if f['lectureId']==l['id']]
 for i,f in enumerate(fs,nextid):
  p=ps[f['paragraph']];text=''.join(p.xpath('.//w:t/text()',namespaces={'w':W}));assert text==f['original'],(l['id'],f['id'],text)
  for run in p.findall('.//{'+W+'}r'):
   if not run.find('.//{'+W+'}t') is None:
    rp=run.find('{'+W+'}rPr')
    if rp is None:rp=node('rPr');run.insert(0,rp)
    h=rp.find('{'+W+'}highlight')
    if h is None:h=node('highlight');rp.append(h)
    h.set('{'+W+'}val','yellow')
  start=node('commentRangeStart',id=i);end=node('commentRangeEnd',id=i)
  p.insert(1 if len(p) and p[0].tag=='{'+W+'}pPr' else 0,start);p.append(end)
  rr=node('r');rp=node('rPr');rp.append(node('rStyle',val='CommentReference'));rr.append(rp);rr.append(node('commentReference',id=i));p.append(rr)
  c=node('comment',id=i,author='Anatomy Evidence Lab AI Review',initials='AI',date='2026-10-01T00:00:00Z')
  lines=[f"{f['id'].upper()} | {f['title']} | FACULTY REVIEW REQUIRED",f"Possible issue: {f['explanation']}",f"Suggested wording: {f['suggestion']}"]
  lines += [f"Evidence: {s['publisher']} — {s['title']}\n{s['url']}" for s in f['sources']]
  lines+=['Please accept, revise or reject this suggestion. Original text is unchanged.']
  for line in lines:
   cp=node('p');pr=node('pPr');pr.append(node('spacing',after=100));cp.append(pr)
   for j,segment in enumerate(line.split('\n')):
    cr=node('r')
    if j:cr.append(node('br'))
    t=node('t');t.text=segment;cr.append(t);cp.append(cr)
   c.append(cp)
  comments.append(c)
 rel=E.fromstring(parts['word/_rels/document.xml.rels'])
 if not any(e.get('Type','').endswith('/comments') for e in rel):
  rid='rIdEvidenceComments';assert not any(e.get('Id')==rid for e in rel)
  E.SubElement(rel,'{'+R+'}Relationship',Id=rid,Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments',Target='comments.xml')
 ct=E.fromstring(parts['[Content_Types].xml'])
 if not any(e.get('PartName')=='/word/comments.xml' for e in ct):E.SubElement(ct,'{'+CT+'}Override',PartName='/word/comments.xml',ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml')
 parts.update({'word/document.xml':xml(d),'word/comments.xml':xml(comments),'word/_rels/document.xml.rels':xml(rel),'[Content_Types].xml':xml(ct)})
 filename=l['filename'].replace('.docx',' - With Comments.docx').replace(' ','_')
 dst=OUT/filename
 with zipfile.ZipFile(dst,'w',zipfile.ZIP_DEFLATED) as z:
  for n,b in parts.items():z.writestr(n,b)
 with zipfile.ZipFile(dst) as z:
  doc=E.fromstring(z.read('word/document.xml'));cs=E.fromstring(z.read('word/comments.xml'))
  assert [''.join(p.xpath('.//w:t/text()',namespaces={'w':W})) for p in doc.findall('.//{'+W+'}p')]==[''.join(p.xpath('.//w:t/text()',namespaces={'w':W})) for p in ps]
  for tag in ['commentRangeStart','commentRangeEnd','commentReference']:
   ids={int(x.get('{'+W+'}id')) for x in doc.findall('.//{'+W+'}'+tag)};assert set(range(nextid,nextid+len(fs)))<=ids
  assert len(cs)==nextid+len(fs)
 shutil.copyfile(dst,ROOT/'public/documents'/f"{l['id']}-comments.docx")
 index+=['',f"Lecture {l['number']} — {l['title']}: {len(fs)} findings",filename]
 for f in fs:index += [f"{f['id'].upper()} | paragraph {f['paragraph']+1} | {f['title']}",f"Issue: {f['explanation']}",f"Suggestion: {f['suggestion']}",*['Evidence: '+s['url'] for s in f['sources']]]
 print(l['number'],len(fs),dst.name)
(OUT/'Review_Index.txt').write_text('\n'.join(index))
with zipfile.ZipFile(OUT/'Lecture_Notes_With_Comments.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(OUT.iterdir()):
  if p.suffix in ['.docx','.txt']:z.write(p,p.name)
shutil.copyfile(OUT/'Lecture_Notes_With_Comments.zip',ROOT/'public/documents/Lecture_Notes_With_Comments.zip')
print('Verified comment anchors and preserved original text for all ten documents.')
