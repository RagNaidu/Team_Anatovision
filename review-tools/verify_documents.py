"""Verify original wording, native comment anchors and per-lecture finding counts."""
import json, zipfile
from pathlib import Path
from lxml import etree as E
ROOT = Path(__file__).resolve().parents[1]
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
lectures = json.loads((ROOT/'data/lectures.json').read_text())
findings = json.loads((ROOT/'data/findings.json').read_text())
assert len({f['id'] for f in findings}) == len(findings), 'Duplicate finding IDs'
for lecture in lectures:
    flags = [f for f in findings if f['lectureId'] == lecture['id']]
    with zipfile.ZipFile(ROOT/'public/documents'/f"{lecture['id']}.docx") as a, zipfile.ZipFile(ROOT/'public/documents'/f"{lecture['id']}-comments.docx") as b:
        original = E.fromstring(a.read('word/document.xml'))
        edited = E.fromstring(b.read('word/document.xml'))
        assert original.xpath('//w:t/text()', namespaces=NS) == edited.xpath('//w:t/text()', namespaces=NS), lecture['id']
        comments = E.fromstring(b.read('word/comments.xml'))
        ids = sorted(comments.xpath('//w:comment/@w:id', namespaces=NS))
        assert len(ids) == len(flags), lecture['id']
        for tag in ['commentRangeStart', 'commentRangeEnd', 'commentReference']:
            assert ids == sorted(edited.xpath('//w:'+tag+'/@w:id', namespaces=NS)), (lecture['id'],tag)
        paragraphs = original.xpath('//w:p', namespaces=NS)
        for f in flags:
            assert ''.join(paragraphs[f['paragraph']].xpath('.//w:t/text()', namespaces=NS)) == f['original'], f['id']
    print(lecture['id'], len(flags), 'verified comments')
with zipfile.ZipFile(ROOT/'public/documents/Lecture_Notes_With_Comments.zip') as z:
    assert len([n for n in z.namelist() if n.endswith('.docx')]) == len(lectures)
print('All document checks passed.')
