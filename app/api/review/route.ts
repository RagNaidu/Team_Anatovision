import { database } from '@/lib/database';
import lectures from '@/data/lectures.json';
import findings from '@/data/findings.json';
const ids = new Set([...lectures.map(l=>l.id), ...findings.map(f=>f.id)]);
export async function GET() {
 try { const r=await database().prepare('SELECT id,status,note,updated_at FROM review_state').all<{id:string,status:string,note:string,updated_at:string}>(); const decisions=new Map(r.results.map(row=>[row.id,row.status])); const records=r.results.map(row=>row.status==='approved'&&findings.some(f=>f.lectureId===row.id&&!['accepted','rejected'].includes(decisions.get(f.id)||''))?{...row,status:'draft'}:row); return Response.json({records}); }
 catch(e) { console.error(e);return Response.json({error:'Review storage is unavailable. Please retry.'},{status:503}); }
}
export async function POST(request:Request) {
 if (request.headers.get('origin') !== new URL(request.url).origin) return Response.json({error:'Invalid origin'},{status:403});
 try {
 const v=await request.json() as {id:string,status:string,note?:string};
 if (!ids.has(v.id) || !(v.id.startsWith('lecture-')?['approved','draft']:['accepted','rejected','pending']).includes(v.status)) return Response.json({error:'Invalid review decision'},{status:400});
 if(v.id.startsWith('lecture-') && v.status==='approved') {
  const unresolved=await database().prepare('SELECT id,status FROM review_state').all<{id:string,status:string}>();
  const decisions = new Map(unresolved.results.map(r=>[r.id,r.status]));
  if(findings.some(f=>f.lectureId===v.id && !['accepted','rejected'].includes(decisions.get(f.id)||''))) return Response.json({error:'Resolve each flagged finding before approving this document.'},{status:409});
 }
 const at=new Date().toISOString();
 const batch=[database().prepare('INSERT INTO review_state(id,status,note,updated_at) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,note=excluded.note,updated_at=excluded.updated_at').bind(v.id,v.status,(v.note||'').slice(0,4000),at)];
 const f=findings.find(f=>f.id===v.id);
 if(f) batch.push(database().prepare('DELETE FROM review_state WHERE id=?').bind(f.lectureId));
 await database().batch(batch);
 return Response.json({ok:true,updatedAt:at});
 }catch(e){console.error(e);return Response.json({error:'Could not save your decision. Please retry.'},{status:503});}
}
