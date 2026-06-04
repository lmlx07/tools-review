import requests, json, time, websocket

WS_URL = 'ws://127.0.0.1:9222/devtools/browser/d58e2cc5-cf52-45e7-8d84-78f819a2ae9a'
bws = websocket.create_connection(WS_URL)

def send(cmd, params=None):
    m = {'id': 1, 'method': cmd}
    if params: m['params'] = params
    bws.send(json.dumps(m))
    return json.loads(bws.recv())

result = send('Target.createTarget', {'url': 'https://cdp.autify.cc/'})
target_id = result['result']['targetId']
time.sleep(6)

targets = requests.get('http://127.0.0.1:9222/json').json()
page_ws_url = None
for t in targets:
    if t['id'] == target_id:
        page_ws_url = t['webSocketDebuggerUrl']
        break

page_ws = websocket.create_connection(page_ws_url)
time.sleep(2)

def eval_js(expr):
    page_ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                             'params': {'expression': expr, 'returnByValue': True}}))
    r = json.loads(page_ws.recv())
    return r.get('result', {}).get('result', {}).get('value', str(r))

# Check initial state
print('=== ZH Homepage ===')
print(f'pathname: {eval_js("window.location.pathname")}')
print(f'switch in nav: {eval_js("!!document.querySelector(\'#nav .menus_items #lang-switch\')")}')
print(f'switch in body: {eval_js("!!document.querySelector(\'body > #lang-switch\')")}')

# Click first article link (PJAX navigation)
print('\n=== Clicking article link (PJAX) ===')
eval_js('document.querySelector("a.article-title")?.click()')
time.sleep(5)

print(f'\n=== After PJAX ===')
print(f'pathname: {eval_js("window.location.pathname")}')
print(f'switch in nav: {eval_js("!!document.querySelector(\'#nav .menus_items #lang-switch\')")}')
print(f'switch in body: {eval_js("!!document.querySelector(\'body > #lang-switch\')")}')
print(f'lang-switch count: {eval_js("document.querySelectorAll(\'#lang-switch\').length")}')

# Click another link
print('\n=== Clicking Tags link ===')
eval_js('document.querySelector("a[href=\'/tags/\']")?.click()')
time.sleep(5)

print(f'\n=== After second PJAX ===')
print(f'pathname: {eval_js("window.location.pathname")}')
print(f'switch in nav: {eval_js("!!document.querySelector(\'#nav .menus_items #lang-switch\')")}')
print(f'switch in body: {eval_js("!!document.querySelector(\'body > #lang-switch\')")}')

page_ws.close()
send('Target.closeTarget', {'targetId': target_id})
bws.close()
