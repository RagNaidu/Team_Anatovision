export async function reviewAccess(request: Request, env: {REVIEW_USERNAME?: string; REVIEW_PASSWORD?: string}, localDevelopment = false): Promise<Response | null> {
  if (localDevelopment) return null;
  if (!env.REVIEW_USERNAME || !env.REVIEW_PASSWORD) {
    return new Response('Reviewer access has not been configured.', {status: 503, headers: {'Cache-Control': 'no-store'}});
  }
  let supplied = '';
  const header = request.headers.get('Authorization') || '';
  if (/^Basic /i.test(header)) {
    try { supplied = atob(header.slice(6)); } catch { /* Invalid credentials. */ }
  }
  const digest = async (s: string) => new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s)));
  const [a, b] = await Promise.all([digest(supplied), digest(`${env.REVIEW_USERNAME}:${env.REVIEW_PASSWORD}`)]);
  let mismatch = 0;
  for (let i = 0; i < a.length; i++) mismatch |= a[i] ^ b[i];
  if (mismatch) return new Response('Reviewer sign-in required.', {status: 401, headers: {
    'WWW-Authenticate': 'Basic realm="Anatomy Evidence Lab", charset="UTF-8"',
    'Cache-Control': 'no-store',
  }});
  return null;
}
