import handler from 'vinext/server/fetch-handler';
import { reviewAccess } from './review-auth.mts';

export default {
  async fetch(request: Request, env: Cloudflare.Env, ctx: ExecutionContext) {
    const denied = await reviewAccess(request, env, import.meta.env.DEV);
    if (denied) return denied;
    // All assets, including lecture downloads, pass through the reviewer gate.
    const canServeAsset = ['GET', 'HEAD'].includes(request.method) && !new URL(request.url).pathname.startsWith('/api/');
    const asset = canServeAsset ? await env.ASSETS.fetch(request) : null;
    const response = !asset || asset.status === 404 ? await handler.fetch(request, env, ctx) : asset;
    const headers = new Headers(response.headers);
    headers.set('Cache-Control', 'private, no-store');
    headers.set('X-Content-Type-Options', 'nosniff');
    return new Response(response.body, {status: response.status, statusText: response.statusText, headers});
  },
};
