/**
 * Extract interactive elements from the page with injected IDs.
 *
 * Inspired by browser-use (https://github.com/browser-use/browser-use).
 *
 * This script:
 * 1. Finds all interactive elements (buttons, links, inputs, etc.)
 * 2. Injects a unique `data-browser-agent-id` attribute into each
 * 3. Returns element data with bounding boxes for LLM matching
 * 4. Recursively extracts elements from iframes (SCORM, embedded content, etc.)
 *
 * IFRAME HANDLING:
 * - Extracts from main document first
 * - Then recursively extracts from all accessible iframes
 * - Each element tracks its frame context via `frame` field
 * - Cross-origin iframes are skipped (browser security restriction)
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

    /**
     * Get clean text content from an element.
     * Handles inputs, contenteditable divs, and regular elements.
     *
     * @param {Element} el - The element to extract text from
     * @param {Document} document - The document context (for getElementById lookups)
     * @returns {string} Clean text content
     */
    function getText(el, document) {
        // For inputs, get value or placeholder
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
            return el.value || el.placeholder || '';
        }
        // For contenteditable divs (like Twitter's reply box), check for placeholder
        if (el.getAttribute('contenteditable') === 'true' || el.getAttribute('role') === 'textbox') {
            // Try direct placeholder attributes first
            const directPlaceholder = el.getAttribute('data-placeholder') ||
                                     el.getAttribute('placeholder') ||
                                     el.getAttribute('aria-placeholder');
            if (directPlaceholder) return directPlaceholder;

            // Check aria-describedby (Twitter's approach - placeholder in separate element)
            const describedBy = el.getAttribute('aria-describedby');
            if (describedBy) {
                const placeholderEl = document.getElementById(describedBy);
                if (placeholderEl) {
                    const placeholderText = placeholderEl.innerText || placeholderEl.textContent || '';
                    if (placeholderText.trim()) return placeholderText.trim();
                }
            }
        }
        // For other elements, get inner text
        const text = el.innerText || el.textContent || '';
        return text.trim().replace(/\s+/g, ' ').substring(0, 80);
    }

    /**
     * Extract interactive elements from a document context (main page or iframe).
     *
     * This function is reusable across different document contexts - it works on
     * the main page document as well as iframe contentDocuments.
     *
     * @param {Document} document - The document to extract from (main or iframe)
     * @param {string} frameContext - Frame identifier ('main' or iframe name/id)
     * @param {Window} window - The window context for computed styles
     * @returns {Array} Array of extracted element objects
     */
    function extractFromDocument(document, frameContext, window) {
        const elements = [];

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
            const text = getText(el, document);
            const ariaLabel = el.getAttribute('aria-label');

            // Get placeholder (including from aria-describedby reference)
            let placeholder = el.placeholder || el.getAttribute('data-placeholder') || el.getAttribute('aria-placeholder');
            if (!placeholder && (el.getAttribute('contenteditable') === 'true' || el.getAttribute('role') === 'textbox')) {
                const describedBy = el.getAttribute('aria-describedby');
                if (describedBy) {
                    const placeholderEl = document.getElementById(describedBy);
                    if (placeholderEl) {
                        placeholder = (placeholderEl.innerText || placeholderEl.textContent || '').trim();
                    }
                }
            }

            if (!text && !ariaLabel && !placeholder && tag !== 'input') return;

            // Skip very small elements (likely icons)
            const rect = el.getBoundingClientRect();
            if (rect.width < 20 && rect.height < 20 && !text) return;

            // Check visibility
            if (!isVisible(el)) return;

            // INJECT a unique ID attribute for reliable location
            const highlightId = String(index);
            el.setAttribute('data-browser-agent-id', highlightId);

            elements.push({
                index: index++,
                tag: tag,
                text: text,
                role: role,
                aria_label: el.getAttribute('aria-label'),
                placeholder: placeholder || null,
                input_type: el.type || null,
                href: (tag === 'a' && el.href) ? el.href.substring(0, 100) : null,
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height),
                frame: frameContext,  // Track which frame this element belongs to
                locator: `[data-browser-agent-id="${highlightId}"]`
            });
        });

        return elements;
    }

    // Extract from main document
    const mainElements = extractFromDocument(document, 'main', window);
    results.push(...mainElements);

    // Extract from all iframes recursively
    const iframes = document.querySelectorAll('iframe');
    let iframeCount = 0;
    let accessibleIframes = 0;
    let iframeElements = 0;

    iframes.forEach((iframe, i) => {
        iframeCount++;
        try {
            // Attempt to access iframe content
            const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
            const iframeWin = iframe.contentWindow;

            if (iframeDoc && iframeWin) {
                accessibleIframes++;
                // Use iframe's name/id as context, or fallback to index
                const frameId = iframe.name || iframe.id || `iframe-${i}`;
                const frameElements = extractFromDocument(iframeDoc, frameId, iframeWin);
                iframeElements += frameElements.length;
                results.push(...frameElements);
            }
        } catch (e) {
            // Cross-origin iframe - browser security prevents access
            // This is expected and safe to skip
        }
    });

    // Add debug info as a comment in console (for debugging only - not in results)
    if (typeof console !== 'undefined') {
        console.log(`[extract_elements] Main: ${mainElements.length} elements, Iframes: ${iframeCount} found, ${accessibleIframes} accessible, ${iframeElements} elements extracted`);
    }

    return results;
})()
