(args) => {
  const normalize = value => (value || '').replace(/\s+/g, ' ').trim();
  const hash = text => {
    let value = 2166136261;
    for (let i = 0; i < text.length; i++) value = Math.imul(value ^ text.charCodeAt(i), 16777619);
    return (value >>> 0).toString(16).padStart(8, '0');
  };
  if (location.protocol !== 'https:' || !['www.tiktok.com', 'tiktok.com'].includes(location.hostname)) {
    return {ok: false, reason: 'wrong_page', items: []};
  }
  const heading = document.querySelector('[data-e2e="login-title"]');
  const rect = heading && heading.getBoundingClientRect();
  const text = heading && normalize(heading.textContent);
  const style = heading && getComputedStyle(heading);
  const visible = rect && rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 &&
    rect.top < innerHeight && rect.left < innerWidth && style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
  if (!/^\/login\/?$/.test(location.pathname) || !visible || !text) {
    // No upload selectors were observed behind login. An unknown surface must
    // never be promoted to ready because a generic file input happens to exist.
    return {ok: false, reason: 'unverified_surface', items: [], submit_supported: false};
  }
  const item = {id: 'tiktok-login', author: 'TikTok', title: text, text, text_hash: hash(text),
    action_index: null, has_action: false,
    visible_bounds: {x: rect.x, y: rect.y, width: rect.width, height: rect.height}};
  if (args && args.expected_item !== undefined) {
    const expected = args.expected_item;
    const ok = Boolean(expected && ['id', 'author', 'title', 'text', 'text_hash'].every(key => expected[key] === item[key]));
    return {ok, reason: ok ? null : 'identity_changed', matched_item: ok ? item : null, scanned: [item]};
  }
  return {ok: false, reason: 'login_required', state: 'login_required', selected_item: item,
    items: [item], submit_supported: false};
}
