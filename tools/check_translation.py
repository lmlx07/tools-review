import requests, json, time, websocket

bws_url = requests.get('http://127.0.0.1:9222/json/version').json().get('webSocketDebuggerUrl')
bws = websocket.create_connection(bws_url)

def send(cmd, params=None):
    m = {'id': 1, 'method': cmd}
    if params: m['params'] = params
    bws.send(json.dumps(m))
    return json.loads(bws.recv())

# Test English article page
result = send('Target.createTarget', {'url': 'https://cdp.autify.cc/en/cdp-python-automation-guide/'})
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

def js(expr):
    page_ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                             'params': {'expression': expr, 'returnByValue': True}}))
    r = json.loads(page_ws.recv())
    return r.get('result', {}).get('result', {}).get('value', str(r))

# Get all visible text from the page
js('''
(function() {
    // Get all text nodes in the article content area
    var article = document.querySelector('#article-container, .article-content, .post-content');
    if (!article) article = document.body;
    var text = article.innerText || article.textContent || '';
    // Find non-ASCII characters (CJK etc.)
    var lines = text.split('\\n');
    var nonEnglish = [];
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line) continue;
        // Check for Chinese/Japanese/Korean chars
        if (/[\\u4e00-\\u9fff\\u3400-\\u4dbf\\uf900-\\ufaff]/.test(line)) {
            nonEnglish.push(line.substring(0, 150));
        }
    }
    return JSON.stringify(nonEnglish.slice(0, 30));
})()
''')
time.sleep(1)

# Read console output - just get the result
r = js('''
(function() {
    var article = document.querySelector('#article-container');
    if (!article) article = document.querySelector('.post-content');
    if (!article) article = document.body;
    var text = article.innerText || article.textContent || '';
    var lines = text.split('\\n');
    var result = [];
    for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line) continue;
        if (/[\\u4e00-\\u9fff\\u3400-\\u4dbf]/.test(line)) {
            result.push(line.substring(0, 150));
        }
    }
    return JSON.stringify(result.slice(0, 30));
})()
''')
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
print('Non-English text in article:')
for item in json.loads(r):
    print(f'  - {item}')

page_ws.close()
bws.close()
