import test from 'node:test';
import assert from 'node:assert/strict';
import { reviewAccess } from '../build/review-auth.mts';
const env = { REVIEW_USERNAME: 'reviewer', REVIEW_PASSWORD: 'test-password' };
test('Unconfigured production gate fails closed, including document downloads', async () => {
  for (const path of ['/', '/api/review', '/documents/lecture-01.docx']) {
    assert.equal((await reviewAccess(new Request('https://test.example' + path), {}))?.status, 503);
  }
});
test('Missing, malformed and incorrect credentials are rejected', async () => {
  for (const auth of ['', 'Basic !!!', 'Basic ' + btoa('reviewer:wrong')]) {
    const result = await reviewAccess(new Request('https://test.example', { headers: { Authorization: auth } }), env);
    assert.equal(result?.status, 401);
    assert.ok(result?.headers.get('WWW-Authenticate'));
  }
});
test('Configured credentials allow a reviewer', async () => {
  assert.equal(await reviewAccess(new Request('https://test.example', { headers: { Authorization: 'Basic ' + btoa('reviewer:test-password') } }), env), null);
});
test('Only explicitly selected local development bypasses authentication', async () => {
  assert.equal(await reviewAccess(new Request('http://localhost'), {}, true), null);
});
