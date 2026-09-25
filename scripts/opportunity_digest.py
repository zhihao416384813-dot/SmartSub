#!/usr/bin/env python3
"""Evidence-linked Telegram digest; no paid API or third-party dependency."""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

TZ = dt.timezone(dt.timedelta(hours=8))
NOW = dt.datetime.now(TZ)
UA = {'User-Agent': 'SmartSub-opportunity-digest/1.0'}
QUERIES = [
    ('AI与开源', 'AI agent 开源 GitHub 中国 商业化'),
    ('资产处置线索', '司法拍卖 破产 设备 叉车 CNC 降价'),
    ('付费需求线索', '闲鱼 代找 代办 比价 自动提醒 需求'),
    ('税惠政策', '深圳 企业 税收优惠 申报 site:gov.cn OR site:sz.gov.cn'),
]
REPOS = ['dgtlmoon/changedetection.io', 'apify/crawlee', 'n8n-io/n8n', 'browser-use/browser-use']

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=18) as response:
        return response.read()

def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', '', value or ''))).strip()

def news(section, query):
    rss = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': query + ' when:2d', 'hl': 'zh-CN', 'gl': 'CN', 'ceid': 'CN:zh-Hans'})
    root = ET.fromstring(get(rss))
    results = []
    for item in root.findall('./channel/item')[:8]:
        title = clean(item.findtext('title'))
        link = item.findtext('link') or ''
        published = item.findtext('pubDate') or ''
        filters = {
            '资产处置线索': ('拍卖', '流拍', '破产', '处置', '挂牌'),
            '付费需求线索': ('代找', '代办', '代购', '比价', '求助', '需求'),
            '税惠政策': ('税', '抵扣', '退税', '加计扣除'),
        }
        if section in filters and not any(word in title for word in filters[section]):
            continue
        if title and link.startswith('https://'):
            results.append({'section': section, 'title': title[:130], 'url': link, 'date': published, 'kind': '线索'})
    return results

def releases():
    items = []
    for repo in REPOS:
        try:
            data = json.loads(get('https://api.github.com/repos/' + repo + '/releases/latest'))
            date = data.get('published_at', '')
            if date and (NOW - dt.datetime.fromisoformat(date.replace('Z', '+00:00'))).days <= 7:
                items.append({'section': '监控智能体', 'title': repo + ' ' + clean(data.get('name') or data.get('tag_name')), 'url': data['html_url'], 'date': date[:10], 'kind': '已核对项目发布页'})
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return items

def collect():
    all_items, errors = [], []
    for section, query in QUERIES:
        try:
            all_items.extend(news(section, query)[:4])
        except (OSError, ValueError, ET.ParseError) as error:
            errors.append(section + ': ' + str(error)[:100])
    all_items.extend(releases())
    seen, unique = set(), []
    for item in all_items:
        key = re.sub(r'[^\w]', '', item['title'].lower())[:48]
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    # Never invent opportunities to reach a quota. Rotate sections for a compact digest.
    output = []
    for section in ['AI与开源', '资产处置线索', '监控智能体', '付费需求线索', '税惠政策']:
        output.extend([i for i in unique if i['section'] == section][:2])
    return output[:8], errors

def render(items, errors):
    lines = [f'🗞 <b>豪哥机会情报｜{NOW:%Y-%m-%d}</b>', '来源链接可点开核实。以下为公开信息线索，并非已核实的成交或利润。']
    if not items:
        lines.append('今天没有取得可核验的新线索；不凑数。')
    for section in ['AI与开源', '资产处置线索', '监控智能体', '付费需求线索', '税惠政策']:
        selected = [x for x in items if x['section'] == section]
        lines.append('\n<b>' + html.escape(section) + '</b>')
        if not selected:
            lines.append('暂无可展示的新线索。')
        for x in selected:
            title = html.escape(x['title'])
            url = html.escape(x['url'], quote=True)
            lines.append(f'• <a href="{url}">{title}</a>｜{x["kind"]}')
    lines.append('\n🔎 资产先核对公告、税费、拆运及真实回收报价；需求先找两条实际付费证据。聚合新闻链接可能跳转，原始公告优先。')
    if errors:
        lines.append('⚠️ 部分栏目抓取失败：' + html.escape('、'.join(x.split(':')[0] for x in errors)))
    return '\n'.join(lines)

def send(message):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        raise RuntimeError('Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID')
    url = f'https://api.telegram.org/bot{token}/sendMessage'
    body = urllib.parse.urlencode({'chat_id': chat, 'text': message, 'parse_mode': 'HTML', 'disable_web_page_preview': 'true'}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=25) as response:
        result = json.load(response)
    if not result.get('ok'):
        raise RuntimeError('Telegram rejected the digest')

if __name__ == '__main__':
    items, errors = collect()
    message = render(items, errors)
    if '--dry-run' in sys.argv:
        print(message)
    else:
        send(message)
        print(f'Sent {len(items)} linked items; {len(errors)} source errors')
