/**
 * Extract interactive elements from the page with injected IDs.
 *
 * Inspired by browser-use (https://github.com/browser-use/browser-use).
 *
 * This script:
 * 1. Finds all interactive elements (buttons, links, inputs, etc.)
 * 2. Injects a unique `data-browser-agent-id` attribute into each
 * 3. Returns element data with bounding boxes for LLM matching
 */
(() => {
    const results = [];
    let index = 0;

    // Interactive element types
    const INTERACTIVE_TAGS = new Set([
        'a', 'button', 'input', 'select', 'textarea', 'label',
        'details', 'summary', 'dialog'
    ]);

    const INTERACTIVE_ROLES = new Set([
        'button', 'link', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
        'option', 'radio', 'switch', 'tab', 'checkbox', 'textbox',
        'searchbox', 'combobox', 'listbox', 'slider', 'spinbutton'
    ]);

    // Check if element is visible
    function isVisible(el) {
        const style = window.getComputedStyle(el);
        if (style.display === 'none') return false;
        if (style.visibility === 'hidden') return false;
        if (parseFloat(style.opacity) === 0) return false;

        // Skip visually-hidden accessibility elements
        const className = el.className || '';
        if (typeof className === 'string' &&
            (className.includes('visually-hidden') ||
             className.includes('sr-only') ||
             className.includes('screen-reader'))) {
            return false;
        }

        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return false;

        // Skip elements that are clipped/hidden with CSS tricks
        if (rect.width < 2 || rect.height < 2) return false;

        // Check if in viewport (with some margin)
        const margin = 100;
        if (rect.bottom < -margin) return false;
        if (rect.top > window.innerHeight + margin) return false;
        if (rect.right < -margin) return false;
        if (rect.left > window.innerWidth + margin) return false;

        return true;
    }

    // Get clean text content
    function getText(el) {
        // For inputs, get value or placeholder
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
            return el.value || el.placeholder || '';
        }
        // For other elements, get inner text
        const text = el.innerText || el.textContent || '';
        return text.trim().replace(/\s+/g, ' ').substring(0, 80);
    }

    // Process all elements
    document.querySelectorAll('*').forEach(el => {
        const tag = el.tagName.toLowerCase();
        const role = el.getAttribute('role');

        // Check if interactive
        const isInteractiveTag = INTERACTIVE_TAGS.has(tag);
        const isInteractiveRole = role && INTERACTIVE_ROLES.has(role);
        const isClickable = window.getComputedStyle(el).cursor === 'pointer';
        const hasTabIndex = el.hasAttribute('tabindex') && el.tabIndex >= 0;
        const hasClickHandler = el.onclick !== null || el.hasAttribute('onclick');

        if (!isInteractiveTag && !isInteractiveRole && !isClickable &&
            !hasTabIndex && !hasClickHandler) {
            return;
        }

        // Skip hidden inputs
        if (tag === 'input' && el.type === 'hidden') return;

        // Skip empty elements with no text or useful attributes
        const text = getText(el);
        const ariaLabel = el.getAttribute('aria-label');
        const placeholder = el.placeholder;
        if (!text && !ariaLabel && !placeholder && tag !== 'input') return;

        // Skip very small elements (likely icons)
        const rect = el.getBoundingClientRect();
        if (rect.width < 20 && rect.height < 20 && !text) return;

        // Check visibility
        if (!isVisible(el)) return;

        // INJECT a unique ID attribute for reliable location
        const highlightId = String(index);
        el.setAttribute('data-browser-agent-id', highlightId);

        results.push({
            index: index++,
            tag: tag,
            text: text,
            role: role,
            aria_label: el.getAttribute('aria-label'),
            placeholder: el.placeholder || null,
            input_type: el.type || null,
            href: (tag === 'a' && el.href) ? el.href.substring(0, 100) : null,
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            // Use injected attribute as locator - guaranteed to work!
            locator: `[data-browser-agent-id="${highlightId}"]`
        });
    });

    return results;
})()
