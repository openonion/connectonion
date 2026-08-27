"""Real-driver acceptance for the internal 1.8 async browser core.

Run explicitly while #498 is in progress:

    python -m pytest tests/e2e/test_async_browser_core_real_driver.py -m slow -q

The ordinary matrix deselects slow tests; the 1.8 exact-artifact gate will run
this against an installed wheel and browser before an alpha is promoted.
"""

import asyncio
import gc
import html
import json
import threading
import urllib.parse

import pytest

from connectonion.useful_tools.browser_tools import _async_element_finder
from connectonion.useful_tools.browser_tools._async_browser import (
    ASYNC_BROWSER_AVAILABLE,
    AsyncBrowserCore,
)


@pytest.mark.slow
def test_real_async_driver_keeps_sessions_isolated_and_interleaves(
    tmp_path, monkeypatch
):
    asyncio.run(_exercise_real_async_driver(tmp_path, monkeypatch))


async def _exercise_real_async_driver(tmp_path, monkeypatch):
    if not ASYNC_BROWSER_AVAILABLE:
        pytest.skip("patchright async API is not installed")

    monkeypatch.setenv("CO_BROWSER_PROFILE_DIR", str(tmp_path / "profile"))
    browser = AsyncBrowserCore(headless=True, use_mock_keychain=True)
    loop = asyncio.get_running_loop()
    loop_errors = []
    timings = {"started": loop.time()}
    close_result = None
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))

    try:
        page_script = tmp_path / "verify-page.js"
        page_script.write_text(
            "(args) => ({ ok: document.title === args.title, title: document.title })",
            encoding="utf-8",
        )
        frame_script = tmp_path / "verify-frame.js"
        frame_script.write_text(
            "(args) => ({ ok: document.querySelector(args.selector)?.textContent "
            "=== args.text, text: document.querySelector(args.selector)?.textContent })",
            encoding="utf-8",
        )
        direct_upload = tmp_path / "direct.txt"
        direct_upload.write_text("direct upload", encoding="utf-8")
        chooser_upload = tmp_path / "chooser.txt"
        chooser_upload.write_text("chooser upload", encoding="utf-8")

        await browser.open_browser()
        timings["opened"] = loop.time()
        try:
            pages = {}
            for session, marker in (("A", "alpha"), ("B", "beta")):
                browser._bind_session(session)
                frame_html = (
                    f"<span id=frame-marker>{marker} frame</span>"
                    "<button id=frame-action onclick=\"this.dataset.clicked='yes'\" "
                    "ondblclick=\"this.dataset.doubled='yes'\" "
                    "oncontextmenu=\"event.preventDefault();this.dataset.context='yes'\" "
                    "onmouseover=\"this.dataset.hovered='yes'\">Frame action</button>"
                    "<input id=direct-upload type=file>"
                    "<input id=chooser-upload type=file style='display:none'>"
                    "<button id=upload-trigger "
                    "onclick=\"document.querySelector('#chooser-upload').click()\">"
                    "Upload from computer</button>"
                )
                page_html = (
                    f"<title>{marker}</title><p>{marker}</p>"
                    f"<input id=editor value={marker}>"
                    "<button class=publish onclick=\"this.dataset.clicked='yes'\">Publish</button>"
                    "<select id=country><option>Australia</option></select>"
                    "<label><input id=terms type=checkbox>Accept terms</label>"
                    "<div id=shadow-host></div>"
                    "<script>const root=document.querySelector('#shadow-host').attachShadow({mode:'open'});"
                    "const button=document.createElement('button');button.textContent='Shadow action';"
                    "button.onclick=()=>button.dataset.clicked='yes';root.append(button)</script>"
                    "<div class=row><span class=draft>Draft</span>"
                    "<button class=near onclick=\"this.previousElementSibling.textContent=''\">Send</button></div>"
                    f"<article class=item><span class=body>{marker} item</span></article>"
                    "<a href=https://example.com/one>one</a>"
                    f'<iframe name=editor srcdoc="{html.escape(frame_html, quote=True)}">'
                    "</iframe>"
                )
                await browser.go_to(
                    "data:text/html," + urllib.parse.quote(page_html),
                    purpose="async core acceptance",
                    who=session,
                )
                pages[session] = browser.page

            matcher_started = threading.Event()
            release_matcher = threading.Event()

            def deterministic_match(_page, description, elements):
                if description == "slow publish":
                    matcher_started.set()
                    release_matcher.wait(timeout=3)
                    description = "Publish"
                by_description = {
                    "Publish": lambda element: element.text == "Publish",
                    "Frame action": lambda element: element.text == "Frame action",
                    "Shadow action": lambda element: element.text == "Shadow action",
                    "country": lambda element: element.element_id == "country",
                    "terms": lambda element: element.element_id == "terms",
                }
                return next(
                    element
                    for element in elements
                    if by_description[description](element)
                )

            monkeypatch.setattr(
                _async_element_finder.rules,
                "find_element",
                deterministic_match,
            )

            async def hold_tab_a():
                browser._bind_session("A")
                return await browser.wait(2)

            async def read_tab_b():
                browser._bind_session("B")
                return await browser.get_text()

            held = asyncio.create_task(hold_tab_a())
            await asyncio.sleep(0.05)
            text_b = await asyncio.wait_for(read_tab_b(), timeout=0.5)

            assert "beta" in text_b
            assert held.done() is False
            assert await held == "Waited for 2 seconds"
            timings["interleaved"] = loop.time()
            assert pages["A"] is not pages["B"]

            browser._bind_session("A")
            await browser.page.locator("#editor").focus()
            focused = json.loads(await browser.get_focused_element())
            assert focused["is_editable"] is True
            assert focused["value_preview"] == "alpha"

            browser._bind_session("B")
            assert await browser.count_elements_by_selector(".item") == (
                "1 element match selector: .item"
            )
            assert await browser.get_element_text_by_selector(".body") == "beta item"
            assert await browser.extract_data(".body") == ["beta item"]
            assert await browser.wait_for_text("beta item", timeout=1) == (
                "Found text: 'beta item'"
            )
            assert await browser.get_links_from_page("example.com") == [
                "https://example.com/one"
            ]
            extracted = json.loads(
                await browser.extract_items_by_selector(".item", ".body")
            )
            assert extracted[0]["text"] == "beta item"
            assert extracted[0]["visible_bounds"]["width"] > 0
            assert await browser.set_viewport(1280, 720) == "Viewport set to 1280x720"

            assert "with text: Publish" in await browser.click_element_by_selector(
                ".publish", text="Publish"
            )
            assert (
                await browser.page.locator(".publish").get_attribute("data-clicked")
                == "yes"
            )
            assert "Typed text" in await browser.type_text_by_selector(
                "#editor", "-typed"
            )
            assert await browser.page.locator("#editor").input_value() == "beta-typed"

            assert (await browser.click("Publish")).endswith("button 'Publish'")
            assert (
                await browser.page.locator(".publish").get_attribute("data-clicked")
                == "yes"
            )
            assert await browser.select_option("country", "Australia") == (
                "Selected 'Australia' in country"
            )
            assert await browser.check_checkbox("terms") == "Checked terms"
            assert await browser.page.locator("#terms").is_checked() is True
            assert await browser.wait_for_element("country", timeout=1) == (
                "Element appeared: country"
            )

            shadow_result = await browser.click("Shadow action")
            assert shadow_result.endswith("(shadow DOM)")
            assert (
                await browser.page.locator("#shadow-host").evaluate(
                    "host => host.shadowRoot.querySelector('button').dataset.clicked"
                )
                == "yes"
            )

            assert (
                "in frames matching 'editor'"
                in await browser.click_element_by_selector(
                    "#frame-action", frame_name="editor"
                )
            )
            editor_frame = next(
                frame for frame in browser.page.frames if frame.name == "editor"
            )
            assert (
                await editor_frame.locator("#frame-action").get_attribute(
                    "data-clicked"
                )
                == "yes"
            )
            assert (await browser.double_click("Frame action")).endswith(
                "button 'Frame action'"
            )
            assert (
                await editor_frame.locator("#frame-action").get_attribute(
                    "data-doubled"
                )
                == "yes"
            )
            assert (await browser.right_click("Frame action")).endswith(
                "button 'Frame action'"
            )
            assert (
                await editor_frame.locator("#frame-action").get_attribute(
                    "data-context"
                )
                == "yes"
            )
            assert (await browser.hover("Frame action")).endswith(
                "button 'Frame action'"
            )
            assert (
                await editor_frame.locator("#frame-action").get_attribute(
                    "data-hovered"
                )
                == "yes"
            )

            near_result = await browser.click_element_near_selector(
                ".draft",
                ".near",
                target_text="Send",
                wait_ms=50,
                verify_anchor_text_cleared=True,
            )
            assert "state=anchor_text_cleared" in near_result

            browser._bind_session("A")
            box = await browser.page.locator("#editor").bounding_box()
            clicking = asyncio.create_task(
                browser.mouse_click(
                    int(box["x"] + box["width"] / 2),
                    int(box["y"] + box["height"] / 2),
                )
            )
            await asyncio.sleep(0.05)
            browser._bind_session("B")
            assert "beta" in await asyncio.wait_for(browser.get_text(), timeout=0.5)
            assert clicking.done() is False
            assert (await clicking).startswith("Clicked at (")

            browser._bind_session("A")
            matching = asyncio.create_task(
                browser.find_element_by_description("slow publish")
            )
            while not matcher_started.is_set():
                await asyncio.sleep(0)
            browser._bind_session("B")
            assert "beta" in await asyncio.wait_for(browser.get_text(), timeout=0.5)
            assert matching.done() is False
            release_matcher.set()
            assert (await matching).startswith('[data-browser-agent-id="')

            page_result = json.loads(
                await browser.run_page_script(
                    str(page_script),
                    json.dumps({"title": "beta"}),
                )
            )
            assert page_result == {"ok": True, "title": "beta"}

            frame_result = json.loads(
                await browser.run_frame_script(
                    str(frame_script),
                    json.dumps({"selector": "#frame-marker", "text": "beta frame"}),
                    frame_name="editor",
                )
            )
            assert frame_result["ok"] is True
            assert frame_result["matched_frame"]["name"] == "editor"

            direct_result = json.loads(
                await browser.upload_file_by_selector(
                    "#direct-upload",
                    str(direct_upload),
                    frame_name="editor",
                )
            )
            assert direct_result["uploaded"] is True
            editor_frame = next(
                frame for frame in browser.page.frames if frame.name == "editor"
            )
            assert (
                await editor_frame.locator("#direct-upload").evaluate(
                    "element => element.files[0].name"
                )
                == direct_upload.name
            )

            chooser_result = json.loads(
                await browser.upload_file_after_click_by_selector(
                    "#upload-trigger",
                    str(chooser_upload),
                    text="Upload from computer",
                    frame_name="editor",
                )
            )
            assert chooser_result["uploaded"] is True
            assert (
                await editor_frame.locator("#chooser-upload").evaluate(
                    "element => element.files[0].name"
                )
                == chooser_upload.name
            )
        finally:
            browser._bind_session(None)
            close_result = await browser.close()
            timings["closed"] = loop.time()
            gc.collect()
            await asyncio.sleep(0.1)
    finally:
        loop.set_exception_handler(previous_handler)

    assert close_result == "Browser closed. Session saved for next time."
    assert not loop_errors, {
        "timings": timings,
        "errors": [
            {
                "message": error.get("message"),
                "exception": repr(error.get("exception")),
                "origin": [
                    f"{frame.name}:{frame.lineno}"
                    for frame in (
                        getattr(error.get("future"), "_source_traceback", None) or []
                    )
                    if "patchright" in frame.filename
                ][-4:],
            }
            for error in loop_errors
        ],
    }
