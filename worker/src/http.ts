// JSON responses, errors and CORS (DESIGN §10.2).

export type ErrorCode =
	| 'unauthorized'
	| 'forbidden'
	| 'not_found'
	| 'method_not_allowed'
	| 'rate_limited'
	| 'payload_too_large'
	| 'bad_request'
	| 'unavailable'
	| 'upstream_error'
	| 'internal';

const NO_STORE = { 'cache-control': 'no-store' };

export function json(data: unknown, status = 200, headers: HeadersInit = {}): Response {
	return new Response(JSON.stringify(data), {
		status,
		headers: { 'content-type': 'application/json', ...NO_STORE, ...headers }
	});
}

export function empty(status = 204, headers: HeadersInit = {}): Response {
	return new Response(null, { status, headers: { ...NO_STORE, ...headers } });
}

export function error(
	status: number,
	code: ErrorCode,
	message: string,
	headers: HeadersInit = {}
): Response {
	return json({ error: { code, message } }, status, headers);
}

const ALLOWED_METHODS = 'GET, PUT, POST, OPTIONS';
const ALLOWED_HEADERS = 'authorization, content-type';

export function allowedOrigins(setting: string | undefined): Set<string> {
	return new Set(
		(setting ?? '')
			.split(',')
			.map((o) => o.trim().replace(/\/+$/, ''))
			.filter(Boolean)
	);
}

/** CORS headers for a request's Origin: only listed origins get any. */
export function corsHeaders(request: Request, setting: string | undefined): Record<string, string> {
	const origin = request.headers.get('origin');
	if (!origin || !allowedOrigins(setting).has(origin)) return {};
	return {
		'access-control-allow-origin': origin,
		'access-control-allow-methods': ALLOWED_METHODS,
		'access-control-allow-headers': ALLOWED_HEADERS,
		'access-control-max-age': '600',
		vary: 'Origin'
	};
}

/** Copy of `response` with the CORS headers added. */
export function withCors(response: Response, cors: Record<string, string>): Response {
	if (!Object.keys(cors).length) return response;
	const out = new Response(response.body, response);
	for (const [k, v] of Object.entries(cors)) out.headers.set(k, v);
	return out;
}

/** Parse a JSON body of at most `maxBytes`; null if too big or not JSON (with the reason). */
export async function readJson(
	request: Request,
	maxBytes: number
): Promise<{ ok: true; value: unknown } | { ok: false; response: Response }> {
	const declared = Number(request.headers.get('content-length') ?? '0');
	if (declared > maxBytes) {
		return { ok: false, response: error(413, 'payload_too_large', `Body over ${maxBytes} bytes.`) };
	}
	const text = await request.text();
	if (new TextEncoder().encode(text).length > maxBytes) {
		return { ok: false, response: error(413, 'payload_too_large', `Body over ${maxBytes} bytes.`) };
	}
	try {
		return { ok: true, value: JSON.parse(text) };
	} catch {
		return { ok: false, response: error(400, 'bad_request', 'Body is not valid JSON.') };
	}
}
