(args) => {
  const options = {
    expectedAuthor: args.expected_author || '',
    expectedText: args.expected_text || '',
    expectedHash: args.expected_text_hash || '',
    maxItems: args.maxItems || 8,
    containerSelector: args.containerSelector,
    textSelector: args.textSelector,
    authorSelector: args.authorSelector || '',
    authorAttribute: args.authorAttribute || '',
    actionSelector: args.actionSelector || 'button',
    actionText: args.actionText || ''
  };

  if (!options.containerSelector || !options.textSelector) {
    return {
      ok: false,
      reason: 'containerSelector and textSelector are required',
      scanned: []
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
  const actionMatches = Array.from(document.querySelectorAll(options.actionSelector))
    .filter((el) => isVisible(el) && (!options.actionText || textOf(el) === options.actionText));
  const scanned = [];
  let visibleContainers = 0;
  let textlessContainers = 0;

  for (const container of Array.from(document.querySelectorAll(options.containerSelector))) {
    if (!isVisible(container)) continue;
    visibleContainers += 1;

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

    const textHash = hashText(text);
    const action = actionMatches.find((candidate) => container.contains(candidate));
    const item = {
      item_index: scanned.length,
      author,
      text,
      text_hash: textHash,
      action_index: action ? actionMatches.indexOf(action) : null,
      has_action: Boolean(action)
    };
    scanned.push(item);

    const authorOk = options.expectedAuthor ? compact(author) === compact(options.expectedAuthor) : true;
    const textOk = options.expectedText ? compact(text) === compact(options.expectedText) : true;
    const hashOk = options.expectedHash ? textHash === options.expectedHash : true;

    if (authorOk && textOk && hashOk && action) {
      return {
        ok: true,
        matched_item: item,
        reason: 'matched expected item and found action'
      };
    }

    if (scanned.length >= options.maxItems) break;
  }

  return {
    ok: false,
    reason: 'expected item is not currently visible with an action',
    expected_author: options.expectedAuthor,
    expected_text_hash: options.expectedHash,
    diagnostics: {
      visible_containers: visibleContainers,
      textless_containers: textlessContainers,
      visible_actions: actionMatches.length
    },
    scanned
  };
}
