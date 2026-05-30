"""Remote-assisted login tool — open a login page on the server browser and let a
remote user solve the login challenge (scan QR / enter credentials) over the agent's
ask_user channel, then persist the session for reuse.

Add to an agent:
    from connectonion.useful_tools import remote_login
    agent = Agent("helper", tools=[remote_login])
    # then: "log in to https://x.com/login"

Unifies scan-QR and password login into one perceive→request→apply→re-check loop;
login success is judged by the agent reading the server page (llm_do), never asked of
the user. The agent chooses the login method from the page; the user only supplies
what the server can't: a QR scan confirmation or credentials.
"""
import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from ..llm_do import llm_do
from .ask_user import ask_user
from .browser_tools import BrowserAutomation
from .browser_tools.browser_config import CHROME_DEFAULT_ARGS, IGNORE_DEFAULT_ARGS

_PROFILE = Path.home() / ".co" / "login_agent_profile"
_PAGE_SETTLE_WAIT_MS = 10000
_LOGIN_METHOD_QR = "qr"
_LOGIN_METHOD_CREDENTIALS = "credentials"
_QR_TEXT_MARKERS = (
    "二维码",
    "扫码",
    "扫一扫",
    "scan qr",
    "qr code",
    "scan code",
    "scan with",
    "use your phone to scan",
)
_LOGGED_OUT_TEXT_MARKERS = (
    "登录/注册",
    "注册/登录",
    "请先登录",
    "登录后",
    "未登录",
    "手机号登录",
    "验证码登录",
    "账号登录",
    "密码登录",
    "login/register",
    "sign in",
    "log in",
)

def _open_browser(headless: bool):
    _PROFILE.mkdir(parents=True, exist_ok=True)
    # Clear lock files left by an interrupted previous browser. Each tool call gets
    # its own Playwright objects so sync Playwright never crosses agent threads.
    for f in _PROFILE.glob("Singleton*"):
        f.unlink(missing_ok=True)
    b = BrowserAutomation(use_chrome_profile=True, headless=headless)
    b.playwright = sync_playwright().start()
    b.browser = b.playwright.chromium.launch_persistent_context(
        str(_PROFILE), headless=headless, executable_path=None,
        args=CHROME_DEFAULT_ARGS,
        ignore_default_args=IGNORE_DEFAULT_ARGS + ["--use-mock-keychain"],
        timeout=60000,
    )
    b.page = b.browser.new_page()
    b.page.set_default_navigation_timeout(60000)
    b.page.set_viewport_size({"width": 1920, "height": 1200})
    b.page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return b


def _send_shot(agent, browser):
    agent.io.send_image(_screenshot_data_url(browser))


def _screenshot_data_url(browser) -> str:
    png = browser.page.screenshot()
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _page_has_qr_login(browser) -> bool:
    text = (browser.get_text() or "")[:5000].lower()
    if any(marker in text for marker in _QR_TEXT_MARKERS):
        return True

    return bool(browser.page.evaluate("""
        () => {
            const qrText = /(qr\\s*code|qrcode|二维码|扫码|扫一扫|scan\\s*(qr|code)|use\\s+.*phone\\s+.*scan)/i;
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width >= 80
                    && rect.height >= 80
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && Number(style.opacity || 1) > 0;
            };
            const attrsOf = (el) => [
                el.id,
                el.getAttribute('class'),
                el.getAttribute('alt'),
                el.getAttribute('aria-label'),
                el.getAttribute('title'),
                el.getAttribute('src'),
                el.getAttribute('data-testid'),
            ].filter(Boolean).join(' ');
            const nodes = Array.from(document.querySelectorAll(
                'img, canvas, svg, [class*="qr" i], [id*="qr" i], [aria-label*="qr" i], [alt*="qr" i], [title*="qr" i], [src*="qr" i], [data-testid*="qr" i]'
            ));
            return nodes.some((el) => {
                if (!visible(el)) return false;
                const rect = el.getBoundingClientRect();
                const squareish = Math.abs(rect.width - rect.height) <= Math.max(rect.width, rect.height) * 0.25
                    && rect.width >= 120
                    && rect.height >= 120
                    && rect.width <= 700
                    && rect.height <= 700;
                const nearestText = (el.closest('form, section, main, article, div') || document.body).innerText || '';
                return qrText.test(attrsOf(el)) || (squareish && qrText.test(nearestText));
            });
        }
    """))


def _page_has_credential_login(browser) -> bool:
    text = (browser.get_text() or "")[:5000].lower()
    if "密码" in text or "password" in text:
        return True

    return bool(browser.page.evaluate("""
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 0
                    && rect.height > 0
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && Number(style.opacity || 1) > 0;
            };
            return Array.from(document.querySelectorAll('input')).some((el) => {
                const type = (el.getAttribute('type') || '').toLowerCase();
                const label = [
                    el.getAttribute('placeholder'),
                    el.getAttribute('aria-label'),
                    el.name,
                    el.id,
                ].filter(Boolean).join(' ');
                return visible(el) && (
                    type === 'password'
                    || /(password|密码|account|账号|email|邮箱|phone|手机|手机号)/i.test(label)
                );
            });
        }
    """))


def _page_has_login_entry(browser) -> bool:
    text = (browser.get_text() or "")[:5000].lower()
    if any(marker in text for marker in _LOGGED_OUT_TEXT_MARKERS):
        return True

    return bool(browser.page.evaluate("""
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 0
                    && rect.height > 0
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && Number(style.opacity || 1) > 0;
            };
            const textOf = (el) => (
                el.innerText
                || el.value
                || el.getAttribute('aria-label')
                || el.getAttribute('title')
                || ''
            ).replace(/\\s+/g, '').trim();
            const loginText = /^(登录|登入|登录\\/注册|注册\\/登录|login|log in|signin|sign in)$/i;
            return Array.from(document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"], div, span'))
                .some((el) => {
                    const text = textOf(el);
                    return visible(el)
                        && text
                        && !/退出登录|logout|log out|sign out/i.test(text)
                        && loginText.test(text);
                });
        }
    """))


def _open_login_entry_if_needed(browser) -> bool:
    if not _page_has_login_entry(browser):
        return False

    clicked = browser.page.evaluate("""
        () => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 0
                    && rect.height > 0
                    && style.display !== 'none'
                    && style.visibility !== 'hidden'
                    && Number(style.opacity || 1) > 0;
            };
            const textOf = (el) => (
                el.innerText
                || el.value
                || el.getAttribute('aria-label')
                || el.getAttribute('title')
                || ''
            ).replace(/\\s+/g, '').trim();
            const loginText = /^(登录|登入|登录\\/注册|注册\\/登录|login|log in|signin|sign in)$/i;
            const el = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="button"], input[type="submit"], div, span'))
                .find((node) => {
                    const text = textOf(node);
                    return visible(node)
                        && text
                        && !/退出登录|logout|log out|sign out/i.test(text)
                        && loginText.test(text);
                });
            if (!el) return false;
            el.click();
            return true;
        }
    """)
    if clicked:
        browser.page.wait_for_timeout(_PAGE_SETTLE_WAIT_MS)
        return True

    return False


def _parse_credentials(answer):
    if isinstance(answer, dict):
        data = answer
    elif isinstance(answer, str) and answer.strip().startswith("{"):
        data = json.loads(answer)
    else:
        data = {}

    username = str(data.get("username") or data.get("account") or data.get("email") or "").strip()
    password = str(data.get("password") or "").strip()
    if username and password:
        return username, password

    lines = [line.strip() for line in str(answer).splitlines() if line.strip()]
    kv = {}
    for line in lines:
        if ":" in line:
            key, value = line.split(":", 1)
            kv[key.strip().lower()] = value.strip()
    username = username or kv.get("username") or kv.get("account") or kv.get("email") or kv.get("账号") or kv.get("邮箱")
    password = password or kv.get("password") or kv.get("密码")
    if not username and lines:
        username = lines[0]
    if not password and len(lines) > 1:
        password = lines[1]
    if username and password:
        return username.strip(), password.strip()

    raise ValueError("missing username or password")


def _ask_credentials(agent, question="请输入账号和密码"):
    agent.io.send({
        "type": "ask_user",
        "question": question,
        "options": [],
        "multi_select": False,
        "input_type": "credentials",
        "fields": [
            {
                "name": "username",
                "label": "账号",
                "type": "text",
                "required": True,
                "autocomplete": "username",
            },
            {
                "name": "password",
                "label": "密码",
                "type": "password",
                "required": True,
                "autocomplete": "current-password",
            },
        ],
    })
    return _parse_credentials(agent.io.receive().get("answer", ""))


def _is_logged_in(browser) -> bool:
    # Login success is the server page's objective state — the agent reads it, not the user.
    text = (browser.get_text() or "")[:3000]
    if _page_has_qr_login(browser) or _page_has_credential_login(browser) or _page_has_login_entry(browser):
        return False

    verdict = llm_do(
        f"网站当前 URL：{browser.page.url}\n页面可见文本（截断）：\n{text}\n\n"
        "判断用户是否已登录成功：不在登录页/扫码页/账号密码输入页、已进入正常使用界面即为已登录。"
        "注意：公开可浏览页面不等于已登录；如果页面仍有登录/注册入口、登录墙、扫码或账号密码输入，即为未登录。"
        "只回答一个词：yes 或 no。",
        model="co/gemini-2.5-flash",
    )
    return "yes" in verdict.strip().lower()


def _classify_login_method(agent, browser) -> str:
    """Use the agent LLM's visual perception for the QR/password branch.

    DOM and text checks are allowed to open a likely login entry, but they do
    not decide that a page is QR login. If the model is unavailable or unclear,
    fail the tool call instead of silently choosing a different login path.
    """
    llm = getattr(agent, "llm", None)
    if llm is None:
        raise RuntimeError("remote_login requires agent.llm for login method classification")

    text = (browser.get_text() or "")[:3000]

    prompt = (
        f"当前 URL：{browser.page.url}\n"
        f"页面可见文本（截断）：\n{text}\n\n"
        "你在判断远程登录页面当前应该走哪种用户协助方式。"
        "请看截图：只有当截图里清楚显示用于登录/验证的可扫描二维码、扫码登录面板、"
        "或明确要求用户用手机扫码的二维码时，回答 yes。"
        "如果是账号密码、手机号、验证码输入、普通登录按钮、公开页面、或只有二维码文字但没有可扫二维码，回答 no。"
        "只回答一个词：yes 或 no。"
    )

    response = llm.complete(
        [
            {"role": "system", "content": "You are a careful visual classifier for browser login states."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": _screenshot_data_url(browser)}},
                ],
            },
        ],
        tools=None,
        temperature=0,
        max_tokens=5,
    )

    verdict = (response.content or "").strip().lower()
    if verdict.startswith("yes"):
        return _LOGIN_METHOD_QR
    if verdict.startswith("no"):
        return _LOGIN_METHOD_CREDENTIALS
    raise RuntimeError(f"unexpected remote_login classifier response: {response.content!r}")


def _fill_password(agent, browser, question="请输入账号和密码"):
    username, password = _ask_credentials(agent, question)
    browser.click("用户名/账号输入框")
    browser.keyboard_type(username)
    browser.click("密码输入框")
    browser.keyboard_type(password)
    browser.click("登录按钮")


def _handle_login_step(agent, browser, failed_attempt=False):
    if not _page_has_qr_login(browser) and not _page_has_credential_login(browser):
        _open_login_entry_if_needed(browser)

    if _classify_login_method(agent, browser) == _LOGIN_METHOD_QR:
        _send_shot(agent, browser)
        question = "登录失败，请重新扫描上面的二维码，完成后点这里" if failed_attempt else "请用手机扫描上面的二维码，完成后点这里"
        ask_user(agent, question, ["扫好了"])
    else:
        if failed_attempt:
            _send_shot(agent, browser)
        question = "登录失败，请重新输入账号和密码" if failed_attempt else "请输入账号和密码"
        _fill_password(agent, browser, question)


def remote_login(agent, url: str) -> str:
    """远程协助登录一个网站并记住登录态。打开 url，若已登录就直接复用；否则由 agent 判断
    当前页面是扫码还是账号密码登录，成功后持久化供下次复用。url 是登录页地址，例如
    https://x.com/login。"""
    browser = _open_browser(False)  # headed（自带 Chromium）；服务器无显示器时改 True
    try:
        browser.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        browser.page.wait_for_timeout(_PAGE_SETTLE_WAIT_MS)

        if _is_logged_in(browser):
            return f"已登录 {url}（复用已存登录态）"

        _handle_login_step(agent, browser)
        browser.page.wait_for_timeout(3000)
        attempts = 0
        while not _is_logged_in(browser):
            attempts += 1
            if attempts > 4:
                _send_shot(agent, browser)
                return f"登录多次未成功，请人工检查当前页面：{url}"
            _handle_login_step(agent, browser, failed_attempt=True)
            browser.page.wait_for_timeout(3000)

        browser._save_context()
        return f"登录成功（agent 已核验页面状态），登录态已保存，下次自动复用：{url}"
    finally:
        browser.close()
