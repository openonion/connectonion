export const CONTROL_CENTER_BRIDGE_VERSION = 1;
const PREFIX = 'connectonion.control-center/';
const REVISION = /^sha256:[a-f0-9]{64}$/;
const ID = /^[A-Za-z0-9._:-]{1,128}$/;
const MAX_BYTES = 2 * 1024 * 1024;
/** Keep recent complete normalized items; signal when older/oversize items are omitted. */
export function boundControlSnapshot(value) {
    const items = [];
    let bytes = 0, truncated = value.truncated ?? false;
    for (const item of value.chatItems.slice(-2000).reverse()) {
        const size = new TextEncoder().encode(JSON.stringify(item)).byteLength;
        if (bytes + size > 1024 * 1024) {
            truncated = true;
            continue;
        }
        bytes += size;
        items.push(item);
    }
    return { ...value, chatItems: items.reverse(), skills: value.skills.slice(0, 2000).map(skill => ({
            name: skill.name.slice(0, 64), ...(skill.description ? { description: skill.description.slice(0, 256) } : {}),
        })), truncated: truncated || items.length !== value.chatItems.length };
}
function copy(value) {
    const raw = JSON.stringify(value);
    if (new TextEncoder().encode(raw).byteLength > MAX_BYTES)
        throw new Error('Control Center frame exceeds size limit');
    return JSON.parse(raw);
}
function object(value) {
    return !!value && typeof value === 'object' && !Array.isArray(value);
}
function validSnapshot(value) {
    return object(value) && (value.sessionId === null || typeof value.sessionId === 'string')
        && typeof value.agentAddress === 'string' && Array.isArray(value.chatItems)
        && value.chatItems.length <= 2000 && Array.isArray(value.skills) && value.skills.length <= 2000
        && value.skills.every((skill) => object(skill) && typeof skill.name === 'string')
        && ['idle', 'working', 'waiting'].includes(value.status)
        && ['disconnected', 'connected', 'reconnecting'].includes(value.connectionState);
}
function scope(revision, epoch) {
    if (!REVISION.test(revision) || !ID.test(epoch))
        throw new Error('Invalid Control Center bridge scope');
    return { version: CONTROL_CENTER_BRIDGE_VERSION, revision, epoch };
}
function scoped(value, revision, epoch) {
    if (!object(value) || value.version !== 1 || value.revision !== revision || value.epoch !== epoch)
        return false;
    try {
        return new TextEncoder().encode(JSON.stringify(value)).byteLength <= MAX_BYTES;
    }
    catch {
        return false;
    }
}
/** Parent supplies its SDK's normalized state and actions. One host per iframe load. */
export function createControlCenterHost(port, options) {
    const envelope = scope(options.revision, options.epoch);
    let state = copy(options.snapshot), sequence = 0, closed = false;
    if (!validSnapshot(state))
        throw new Error('Invalid Control Center snapshot');
    const seen = new Set();
    const pending = new Map();
    const send = (message) => {
        if (!closed)
            port.postMessage({ ...envelope, ...message });
    };
    const snapshot = () => send({ type: PREFIX + 'snapshot', sequence: ++sequence, snapshot: state });
    const respond = (id, result, error) => send({
        type: PREFIX + 'response', id, ok: !error, ...(error ? { error: { code: 'action_rejected', message: error } } : { result }),
    });
    port.onmessage = (event) => {
        const value = event.data;
        if (closed || !scoped(value, options.revision, options.epoch))
            return;
        if (value.type === PREFIX + 'resnapshot') {
            snapshot();
            return;
        }
        if (value.type === PREFIX + 'cancel' && typeof value.id === 'string') {
            pending.get(value.id)?.abort();
            pending.delete(value.id);
            return;
        }
        if (value.type !== PREFIX + 'request' || typeof value.id !== 'string' || !ID.test(value.id))
            return;
        const id = value.id;
        if (seen.has(id)) {
            respond(id, undefined, 'Duplicate Control Center request');
            return;
        }
        if (seen.size >= 512 || pending.size >= 16) {
            respond(id, undefined, 'Bridge request capacity reached; reload the app');
            return;
        }
        seen.add(id);
        if (state.connectionState !== 'connected') {
            respond(id, undefined, 'Agent connection is not ready');
            return;
        }
        if (!object(value.payload)) {
            respond(id, undefined, 'Invalid action payload');
            return;
        }
        const target = value.payload.conversation ?? 'current';
        if (target !== 'current' && target !== 'new') {
            respond(id, undefined, 'Invalid conversation target');
            return;
        }
        const controller = new AbortController();
        const context = { id, signal: controller.signal, conversation: target };
        const run = async () => {
            if (value.action === 'send_message') {
                const message = typeof value.payload.message === 'string' ? value.payload.message.trim() : '';
                if (!message || message.length > 10000)
                    throw new Error('Message must contain 1–10000 characters');
                return options.sendMessage(message, context);
            }
            if (value.action !== 'run_skill')
                throw new Error('Unsupported Control Center action');
            const skill = value.payload.skill;
            if (typeof skill !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(skill)
                || !state.skills.some(item => item.name === skill))
                throw new Error('Agent does not publish that skill');
            const args = value.payload.args;
            if (args !== undefined && (typeof args !== 'string' || args.length > 2000))
                throw new Error('Invalid skill arguments');
            return options.runSkill(skill, args, context);
        };
        pending.set(id, controller);
        void run().then(result => {
            if (pending.delete(id) && !controller.signal.aborted)
                respond(id, result);
        }, error => {
            if (pending.delete(id) && !controller.signal.aborted)
                respond(id, undefined, error instanceof Error ? error.message : 'Control Center action failed');
        });
    };
    port.start();
    snapshot();
    return {
        publish(next) {
            if (closed)
                return;
            if (!validSnapshot(next))
                throw new Error('Invalid Control Center snapshot');
            state = copy(next);
            send({ type: PREFIX + 'event', sequence: ++sequence, snapshot: state });
        },
        dispose() {
            closed = true;
            port.onmessage = null;
            for (const controller of pending.values())
                controller.abort();
            pending.clear();
            port.close();
        },
    };
}
/** Child receives a verified private port from its parent; a bare URL has no port. */
export function createControlCenterClient(port, revision, epoch) {
    const envelope = scope(revision, epoch);
    let closed = false, sequence = 0, serial = 0, state = null;
    const listeners = new Set();
    const pending = new Map();
    const send = (value) => { if (!closed)
        port.postMessage({ ...envelope, ...value }); };
    port.onmessage = event => {
        const value = event.data;
        if (closed || !scoped(value, revision, epoch))
            return;
        if (value.type === PREFIX + 'snapshot' || value.type === PREFIX + 'event') {
            if (!Number.isSafeInteger(value.sequence) || value.sequence <= sequence || !validSnapshot(value.snapshot))
                return;
            if (value.type === PREFIX + 'event' && value.sequence !== sequence + 1) {
                send({ type: PREFIX + 'resnapshot' });
                return;
            }
            sequence = value.sequence;
            state = copy(value.snapshot);
            for (const listener of listeners)
                listener(copy(state));
            return;
        }
        if (value.type !== PREFIX + 'response' || typeof value.id !== 'string')
            return;
        const request = pending.get(value.id);
        if (!request)
            return;
        pending.delete(value.id);
        request.cleanup();
        if (value.ok === true && object(value.result) && typeof value.result.sessionId === 'string')
            request.resolve(value.result);
        else
            request.reject(new Error(typeof value.error?.message === 'string' ? value.error.message : 'Control Center action failed'));
    };
    port.start();
    function request(action, payload, options = {}) {
        if (closed)
            return Promise.reject(new Error('Control Center bridge is closed'));
        if (options.signal?.aborted)
            return Promise.reject(new Error('Control Center action cancelled'));
        if (pending.size >= 16)
            return Promise.reject(new Error('Too many pending Control Center actions'));
        const id = 'request-' + (++serial);
        return new Promise((resolve, reject) => {
            const cancel = (message) => {
                const item = pending.get(id);
                if (!item)
                    return;
                pending.delete(id);
                item.cleanup();
                send({ type: PREFIX + 'cancel', id });
                reject(new Error(message));
            };
            const abort = () => cancel('Control Center action cancelled');
            const timer = setTimeout(() => cancel('Control Center action timed out; inspect chat before retrying'), Math.max(1, Math.min(options.timeoutMs ?? 120000, 600000)));
            const cleanup = () => { clearTimeout(timer); options.signal?.removeEventListener('abort', abort); };
            pending.set(id, { resolve, reject, cleanup });
            options.signal?.addEventListener('abort', abort, { once: true });
            send({ type: PREFIX + 'request', id, action, payload: { ...payload, conversation: options.conversation ?? 'current' } });
        });
    }
    return {
        sendMessage: (message, options) => request('send_message', { message }, options),
        runSkill: (skill, args, options) => request('run_skill', { skill, args }, options),
        subscribe(listener) {
            listeners.add(listener);
            if (state)
                listener(copy(state));
            return () => { listeners.delete(listener); };
        },
        resnapshot() { send({ type: PREFIX + 'resnapshot' }); },
        dispose() {
            if (closed)
                return;
            for (const [id, item] of pending) {
                send({ type: PREFIX + 'cancel', id });
                item.cleanup();
                item.reject(new Error('Control Center bridge is closed'));
            }
            closed = true;
            pending.clear();
            listeners.clear();
            port.onmessage = null;
            port.close();
        },
    };
}
/** Connect an embedded app only to its declared parent origin and revision. */
export function connectControlCenter(options) {
    if (typeof window === 'undefined' || window.parent === window) {
        return Promise.reject(new Error('Open this app in an O Chat Control Center session to connect'));
    }
    const origin = new URL(options.parentOrigin);
    const local = options.allowLocalhost === true && origin.protocol === 'http:'
        && ['localhost', '127.0.0.1', '[::1]'].includes(origin.hostname);
    if ((!local && origin.protocol !== 'https:') || origin.origin !== options.parentOrigin || !REVISION.test(options.revision)) {
        return Promise.reject(new Error('Invalid Control Center parent origin or revision'));
    }
    return new Promise((resolve, reject) => {
        const cleanup = () => { clearTimeout(timer); clearInterval(retry); window.removeEventListener('message', receive); };
        const receive = (event) => {
            const value = event.data;
            if (event.source !== window.parent || event.origin !== options.parentOrigin
                || !object(value) || value.type !== PREFIX + 'connect' || value.version !== 1
                || value.revision !== options.revision || typeof value.epoch !== 'string'
                || !ID.test(value.epoch) || event.ports.length !== 1)
                return;
            cleanup();
            resolve(createControlCenterClient(event.ports[0], options.revision, value.epoch));
        };
        const ready = () => window.parent.postMessage({ type: PREFIX + 'ready', version: 1, revision: options.revision }, options.parentOrigin);
        const timer = setTimeout(() => { cleanup(); reject(new Error('Control Center parent did not connect')); }, options.timeoutMs ?? 15000);
        const retry = setInterval(ready, 1000);
        window.addEventListener('message', receive);
        ready();
    });
}
