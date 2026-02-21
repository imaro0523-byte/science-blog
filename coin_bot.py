import os
import json
import time
import re
import requests
import feedparser
import trafilatura
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# =========================================================
# [설정 구역]
# =========================================================
print("🔧 환경변수 점검...")

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')
BLOG_ID = os.environ.get('BLOG_ID')

if not GEMINI_API_KEY or not BLOG_ID:
    print("❌ 필수 환경변수 누락")
    exit(1)

try:
    CLIENT_JSON = json.loads(os.environ.get('CLIENT_JSON', '{}'))
    TOKEN_JSON = json.loads(os.environ.get('TOKEN_JSON', '{}'))
except:
    print("⛔ 인증 토큰 로딩 실패")
    exit(1)

MODEL_NAME = "gemini-2.5-flash"

# =========================================================
# [함수 1] 암호화폐 대시보드
# =========================================================
def get_crypto_dashboard_html():
    print("📊 암호화폐 데이터 수집...")
    crypto_data = {}
    
    try:
        res = requests.get("https://api.coingecko.com/api/v3/simple/price", 
                         params={"ids": "bitcoin,ethereum,binancecoin,ripple,cardano", 
                                "vs_currencies": "krw", "include_24hr_change": "true"}, timeout=10).json()
        
        crypto_data = {
            "btc": {"price": res.get('bitcoin', {}).get('krw', 0), "chg": res.get('bitcoin', {}).get('krw_24h_change', 0), "name": "비트코인"},
            "eth": {"price": res.get('ethereum', {}).get('krw', 0), "chg": res.get('ethereum', {}).get('krw_24h_change', 0), "name": "이더리움"},
            "bnb": {"price": res.get('binancecoin', {}).get('krw', 0), "chg": res.get('binancecoin', {}).get('krw_24h_change', 0), "name": "바이낸스코인"},
            "xrp": {"price": res.get('ripple', {}).get('krw', 0), "chg": res.get('ripple', {}).get('krw_24h_change', 0), "name": "리플"},
            "ada": {"price": res.get('cardano', {}).get('krw', 0), "chg": res.get('cardano', {}).get('krw_24h_change', 0), "name": "카르다노"}
        }
    except:
        for key in ['btc', 'eth', 'bnb', 'xrp', 'ada']:
            crypto_data[key] = {"price": 0, "chg": 0, "name": key.upper()}

    def get_style(chg):
        return ("#d63031", "▲") if chg >= 0 else ("#0984e3", "▼")

    items_html = ""
    for key in ['btc', 'eth', 'bnb', 'xrp', 'ada']:
        color, arrow = get_style(crypto_data[key]['chg'])
        items_html += f'<div style="flex: 1 1 18%; min-width: 100px; margin: 5px; padding: 10px; background: #fff; border-radius: 8px; text-align: center;"><div style="font-size: 11px; color: #888;">{crypto_data[key]["name"]}</div><div style="font-size: 14px; font-weight: 800; color: {color};">{arrow} ₩{crypto_data[key]["price"]:,.0f}</div><div style="font-size: 10px; color: {color};">({crypto_data[key]["chg"]:.2f}%)</div></div>'
    
    return f'<div style="font-family: -apple-system; margin-bottom: 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 15px;"><h3 style="text-align: center; margin: 0 0 10px 0; font-size: 16px; color: white;">🪙 Crypto Market Flow</h3><div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 5px;">{items_html}</div></div>'

# [함수 2-6] 뉴스, 중복, 크롤링, 관련기사, AI분석 (동일)
def get_crypto_news_list():
    print("🔍 암호화폐 뉴스 검색...")
    try:
        feed = feedparser.parse("https://news.google.com/rss/search?q=암호화폐+OR+비트코인+OR+알트코인+when:1d&hl=ko&gl=KR")
        if feed.entries:
            return feed.entries[:10]
    except:
        pass
    return []

def check_is_duplicate(service, news_title):
    try:
        for post in service.posts().list(blogId=BLOG_ID, maxResults=10).execute().get('items', []):
            if news_title in post.get('content', ''):
                return True
    except:
        pass
    return False

def fetch_article_content(url):
    print(f"📰 크롤링...")
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded)
            if text and len(text) > 100:
                print(f"✅ {len(text)}자")
                return text[:2500]
    except:
        pass
    return None

def find_related_articles(target_title, all_news_list):
    print("🔍 비슷한 기사...")
    related = [news for news in all_news_list if news.title != target_title and len(set(news.title.split()) & set(target_title.split())) >= 2][:3]
    combined = ""
    for news in related:
        try:
            text = trafilatura.extract(trafilatura.fetch_url(news.link))
            if text:
                combined += f"\n{text[:600]}\n"
                if len(combined) > 1800:
                    break
        except:
            continue
    return combined if combined else None

def ask_ai_about_crypto(news_title):
    print("🤖 AI 분석...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": f"'{news_title}' 암호화폐 뉴스 5-6문단 심층 분석"}]}]}, timeout=20)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text) > 150:
                return text[:2500]
    except:
        pass
    return None

# =========================================================
# [함수 7] ★ 블록체인/암호화폐 심층 리서치 (핵심!)
# =========================================================
def research_crypto_deeply(news_title, article_content):
    """블록체인 원리, 역사, 규제, 전망 등 심층 분석"""
    print("🔬 블록체인 원리 심층 리서치...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    context = f"기사: {article_content[:1500]}" if article_content else f"제목: {news_title}"
    
    prompt = f"""
    암호화폐 뉴스를 심층 분석하세요.
    
    {context}
    
    다음 항목을 각 3-4문장으로:
    1. 블록체인 기술 원리: 작업증명/지분증명, 스마트 컨트랙트, 합의 알고리즘 등 기술적 메커니즘
    2. 암호화폐 역사: 비트코인 탄생부터 현재까지, 주요 사건 (Mt.Gox 사태, 비트코인 반감기, DeFi 붐 등)
    3. 규제 환경: 각국 정부의 암호화폐 정책, 법적 지위, 규제 동향
    4. 시장 심리: 투자자 sentiment, Fear & Greed Index, 온체인 지표
    5. 미래 전망: DeFi, NFT, Web3 등 미래 응용 가능성
    
    JSON 출력:
    {{
      "blockchain_tech": "...",
      "crypto_history": "...",
      "regulation": "...",
      "market_sentiment": "...",
      "future_outlook": "..."
    }}
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        if res.status_code == 200:
            raw = res.json()['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                print("✅ 리서치 완료")
                return json.loads(match.group())
    except:
        pass
    return None

# [함수 8] 코인 정보
def research_crypto_coins(news_title, article_content):
    print("🪙 코인 리서치...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    context = article_content[:1000] if article_content else news_title
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": f"{context}\n\n관련 코인 2-3개 JSON: {{'coins':[{{'name':'Bitcoin','symbol':'BTC'}}]}}"}]}]}, timeout=15)
        if res.status_code == 200:
            match = re.search(r'\{.*\}', res.json()['candidates'][0]['content']['parts'][0]['text'], re.DOTALL)
            if match:
                return json.loads(match.group())
    except:
        pass
    return None

def get_coin_price_data(coin_symbols):
    print("💰 코인 가격...")
    symbol_to_id = {'BTC':'bitcoin','ETH':'ethereum','BNB':'binancecoin','XRP':'ripple','ADA':'cardano','SOL':'solana','DOT':'polkadot','DOGE':'dogecoin'}
    coin_data = []
    
    for symbol in coin_symbols[:3]:
        coin_id = symbol_to_id.get(symbol.upper(), symbol.lower())
        try:
            res = requests.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}", timeout=10).json()
            coin_data.append({
                'name': res['name'],
                'symbol': res['symbol'].upper(),
                'price': f"₩{res['market_data']['current_price']['krw']:,.0f}",
                'market_cap': f"₩{res['market_data']['market_cap']['krw']/1e12:.2f}조",
                'change_24h': f"{res['market_data']['price_change_percentage_24h']:.2f}%",
                'rank': res['market_cap_rank']
            })
        except:
            continue
    return coin_data

def make_coin_cards(coin_data):
    if not coin_data:
        return ""
    cards = '<div style="display: flex; flex-wrap: wrap; gap: 15px; margin: 25px 0;">'
    for c in coin_data:
        color = "#d63031" if float(c['change_24h'].replace('%', '')) >= 0 else "#0984e3"
        cards += f'<div style="flex: 1 1 calc(50% - 15px); min-width: 250px; background: linear-gradient(135deg, #667eea22, #764ba233); border-radius: 12px; padding: 20px; border-left: 4px solid #667eea;"><h3 style="margin: 0 0 10px 0;">{c["name"]} ({c["symbol"]})</h3><p style="margin: 5px 0; font-size: 13px;"><b>순위:</b> #{c["rank"]}</p><p style="margin: 5px 0; font-size: 13px;"><b>현재가:</b> {c["price"]}</p><p style="margin: 5px 0; font-size: 13px;"><b>시총:</b> {c["market_cap"]}</p><p style="margin: 5px 0; font-size: 13px; color: {color};"><b>24h:</b> {c["change_24h"]}</p></div>'
    cards += '</div>'
    return cards

# [함수 9-11] 키워드, 이미지, 클리너
def get_search_keywords(news_title):
    try:
        res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}", 
                          json={"contents": [{"parts": [{"text": f"'{news_title}' 영어 키워드 2개"}]}]}, timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "cryptocurrency, blockchain"

def get_relevant_images_webp(query):
    if not PEXELS_API_KEY:
        return []
    try:
        resp = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": PEXELS_API_KEY}, params={"query": query, "per_page": 2}, timeout=10)
        if resp.status_code == 200:
            return [p['src']['original']+"?w=800" for p in resp.json().get('photos', [])]
    except:
        pass
    return []

def clean_markdown(text):
    text = re.sub(r'\*\*([^\*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^\*]+)\*', r'<em>\1</em>', text)
    text = text.replace('###', '').replace('##', '').replace('```', '').replace('**', '')
    text = re.sub(r'<i>(\d+)</i>', r'\1', text)
    return re.sub(r'</i>|<i>', '', text)

# =========================================================
# [함수 12] ★ 심층 암호화폐 칼럼
# =========================================================
def generate_deep_crypto_content(news, images, dashboard, article_content, research_data, coin_data):
    print("🧠 심층 암호화폐 칼럼...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    article_part = f"[기사]\n{article_content[:1200]}" if article_content else ""
    
    research_section = ""
    if research_data:
        research_section = f"""
[참고 지식]
- 블록체인 기술: {research_data.get('blockchain_tech', 'N/A')}
- 암호화폐 역사: {research_data.get('crypto_history', 'N/A')}
- 규제 환경: {research_data.get('regulation', 'N/A')}
- 시장 심리: {research_data.get('market_sentiment', 'N/A')}
- 미래 전망: {research_data.get('future_outlook', 'N/A')}
"""
    
    coin_summary = ""
    if coin_data:
        coin_summary = "\n[관련 코인]\n" + "\n".join([f"- {c['name']}({c['symbol']}): #{c['rank']}, {c['price']}" for c in coin_data])
    
    prompt = f"""
    암호화폐 전문 애널리스트로서 교과서 수준의 심층 해설 작성.
    
    [뉴스] {news.title}
    {article_part}
    {research_section}
    {coin_summary}
    
    [가이드 - 깊이 있는 분석]
    1. **블록체인 원리**: 기술을 비전공자도 이해하게
    2. **역사 비교**: 과거 암호화폐 사건과 비교
    3. **규제 분석**: 각국 정책이 미치는 영향
    4. **다각적 관점**: 찬반 의견 모두
    5. **충분한 길이**: 1500자 이상
    
    HTML:
    DASHBOARDHERE
    <h2>🔥 소제목</h2>
    <p>후킹 4문장</p>
    IMAGE1HERE
    <h2>⛓️ 블록체인 기술 원리</h2>
    <p>작동 방식 7문장</p>
    <ul><li>원리 1</li><li>원리 2</li><li>원리 3</li></ul>
    <h2>📖 암호화폐의 역사</h2>
    <p>비트코인부터 현재까지 5문장</p>
    <h2>⚖️ 규제와 법적 지위</h2>
    <p>각국 정책 6문장</p>
    IMAGE2HERE
    <h2>🪙 주목할 코인들</h2>
    <p>코인 분석 4문장</p>
    COINCARDSHERE
    <h2>🚀 미래: DeFi와 Web3</h2>
    <p>미래 응용 5문장</p>
    <h2>⚠️ 투자 리스크</h2>
    <p>위험 요소 4문장</p>
    <p><strong>결론:</strong> 2문장</p>
    <hr><p style="color:grey; font-size:0.85em;">📰 출처: {news.title}<br>⚠️ 투자 책임은 본인에게</p>
    
    규칙: HTML만, 해요체, 4문장 이상/섹션
    """
    
    for attempt in range(3):
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=40)
            if res.status_code == 200:
                clean = clean_markdown(res.json()['candidates'][0]['content']['parts'][0]['text']).replace("```html", "").replace("```", "").strip()
                
                clean = clean.replace("DASHBOARDHERE", dashboard).replace("[[DASHBOARD]]", dashboard)
                clean = clean.replace("COINCARDSHERE", make_coin_cards(coin_data)).replace("[[COIN_CARDS]]", make_coin_cards(coin_data))
                
                img1 = f'<img src="{images[0]}" style="width:100%; border-radius:12px; margin:25px 0;">' if len(images) > 0 else ""
                img2 = f'<img src="{images[1]}" style="width:100%; border-radius:12px; margin:25px 0;">' if len(images) > 1 else img1
                clean = clean.replace("IMAGE1HERE", img1).replace("IMAGE2HERE", img2).replace("[[IMAGE_1]]", img1).replace("[[IMAGE_2]]", img2)
                
                if len(clean) > 1200:
                    print(f"✅ {len(clean)}자")
                    return clean
            time.sleep(3)
        except Exception as e:
            print(f"❌ {attempt+1}: {e}")
            time.sleep(5)
    return None

def generate_title(news_title):
    try:
        res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}", 
                          json={"contents": [{"parts": [{"text": f"'{news_title}' 암호화폐 블로그 제목 1개"}]}]}, timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')[0].replace('"', '').replace('*', '')
    except:
        return news_title

# =========================================================
# [메인]
# =========================================================
def run_bot():
    print("▶️ 암호화폐 심층 분석 봇 (애드센스용)")
    try:
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        news_list = get_crypto_news_list()
        if not news_list:
            return

        target = None
        for news in news_list:
            print(f"\n{'='*60}\n🔎 {news.title[:50]}...")
            if check_is_duplicate(service, news.title):
                print("🚫 중복")
                continue
            target = news
            break
        
        if not target:
            print("😴 새 뉴스 없음")
            return

        print(f"\n✅ 선택: {target.title}\n{'='*60}\n")

        # ★★★ 강화된 파이프라인 ★★★
        article_content = fetch_article_content(target.link)
        if not article_content:
            article_content = find_related_articles(target.title, news_list)
        if not article_content:
            article_content = ask_ai_about_crypto(target.title)
        
        # ★ 심층 리서치
        research_data = research_crypto_deeply(target.title, article_content)
        
        coin_research = research_crypto_coins(target.title, article_content)
        coin_data = []
        if coin_research and 'coins' in coin_research:
            coin_data = get_coin_price_data([c['symbol'] for c in coin_research['coins']])
        
        keywords = get_search_keywords(target.title)
        images = get_relevant_images_webp(keywords)
        dashboard = get_crypto_dashboard_html()
        
        content = generate_deep_crypto_content(target, images, dashboard, article_content, research_data, coin_data)
        if not content:
            print("❌ 작성 실패")
            return

        title = generate_title(target.title)
        print(f"\n📤 제목: {title}")
        
        body = {"kind": "blogger#post", "title": title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"🎉 완료! ({len(content)}자)")

    except Exception as e:
        print(f"⛔ 오류: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    run_bot()
