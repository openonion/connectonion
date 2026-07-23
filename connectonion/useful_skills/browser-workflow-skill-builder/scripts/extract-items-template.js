(args) => {
  const options = {
    maxItems: args.maxItems || 3,
    containerSelector: args.containerSelector,
    textSelector: args.textSelector,
    authorSelector: args.authorSelector || '',
    authorAttribute: args.authorAttribute || '',
    actionSelector: args.actionSelector || 'button',
    actionText: args.actionText || '',
    excludeTextPattern: args.excludeTextPattern || ''
  };

  if (!options.containerSelector || !options.textSelector) {
    return {
      ok: false,
      reason: 'containerSelector and textSelector are required',
      items: [],
      selected_item: null
    };
  }

  const normalize = (value) => String(value || '')
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  const compact = (value) => normalize(value).replace(/\s+/g, ' ');

  const hashText = (value) => {
    const text = compact(value);
    let hash = 2166136261;
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, '0');
  };

  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      rect.width > 0 &&
      rect.height > 0 &&
      rect.bottom > 0 &&
      rect.top < window.innerHeight;
  };

  const textOf = (el) => normalize(el?.innerText || el?.textContent || '');
  const excluded = options.excludeTextPattern ? new RegExp(options.excludeTextPattern, 'i') : null;
  const actionMatches = Array.from(document.querySelectorAll(options.actionSelector))
    .filter((el) => isVisible(el) && (!options.actionText || textOf(el) === options.actionText));

  const items = [];
  let visibleContainers = 0;
  let textlessContainers = 0;
  let excludedContainers = 0;

  for (const container of Array.from(document.querySelectorAll(options.containerSelector))) {
    if (!isVisible(container)) continue;
    visibleContainers += 1;
    if (excluded && excluded.test(textOf(container))) {
      excludedContainers += 1;
      continue;
    }

    const textNode = container.querySelector(options.textSelector);
    const text = textOf(textNode);
    if (!text) {
      textlessContainers += 1;
      continue;
    }

    let author = '';
    if (options.authorSelector) {
      const authorNode = container.querySelector(options.authorSelector);
      author = options.authorAttribute
        ? normalize(authorNode?.getAttribute(options.authorAttribute))
        : textOf(authorNode);
    }

    const action = actionMatches.find((candidate) => container.contains(candidate));
    const rect = container.getBoundingClientRect();

    items.push({
      item_index: items.length,
      author,
      text,
      text_hash: hashText(text),
      action_index: action ? actionMatches.indexOf(action) : null,
      has_action: Boolean(action),
      visible_bounds: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height)
      }
    });

    if (items.length >= options.maxItems) break;
  }

  return {
    ok: items.length > 0,
    reason: items.length > 0 ? 'items extracted' : 'no visible matching items',
    diagnostics: {
      visible_containers: visibleContainers,
      excluded_containers: excludedContainers,
      textless_containers: textlessContainers,
      visible_actions: actionMatches.length
    },
    items,
    selected_item: items[0] || null
  };
}
