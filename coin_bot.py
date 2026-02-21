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
    print("📊 암호화폐 데이터 수집 중...")
    
    # CoinGecko API로 주요 코인 가격 가져오기
    crypto_data = {}
    
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": "bitcoin,ethereum,binancecoin,ripple,cardano",
            "vs_currencies": "krw",
            "include_24hr_change": "true"
        }
        res = requests.get(url, params=params, timeout=10).json()
        
        crypto_data = {
            "btc": {"price": res.get('bitcoin', {}).get('krw', 0), 
                   "chg": res.get('bitcoin', {}).get('krw_24h_change', 0), 
                   "name": "비트코인"},
            "eth": {"price": res.get('ethereum', {}).get('krw', 0), 
                   "chg": res.get('ethereum', {}).get('krw_24h_change', 0), 
                   "name": "이더리움"},
            "bnb": {"price": res.get('binancecoin', {}).get('krw', 0), 
                   "chg": res.get('binancecoin', {}).get('krw_24h_change', 0), 
                   "name": "바이낸스코인"},
            "xrp": {"price": res.get('ripple', {}).get('krw', 0), 
                   "chg": res.get('ripple', {}).get('krw_24h_change', 0), 
                   "name": "리플"},
            "ada": {"price": res.get('cardano', {}).get('krw', 0), 
                   "chg": res.get('cardano', {}).get('krw_24h_change', 0), 
                   "name": "카르다노"}
        }
    except Exception as e:
        print(f"⚠️ 암호화폐 데이터 실패: {e}")
        # 실패 시 빈 데이터
        for key in ['btc', 'eth', 'bnb', 'xrp', 'ada']:
            if key not in crypto_data:
                crypto_data[key] = {"price": 0, "chg": 0, "name": key.upper()}

    def get_style(chg):
        color = "#d63031" if chg >= 0 else "#0984e3"
        arrow = "▲" if chg >= 0 else "▼"
        return color, arrow

    items_html = ""
    for key in ['btc', 'eth', 'bnb', 'xrp', 'ada']:
        color, arrow = get_style(crypto_data[key]['chg'])
        price_fmt = f"{crypto_data[key]['price']:,.0f}"
        
        items_html += f"""
        <div style="flex: 1 1 18%; min-width: 100px; margin: 5px; padding: 10px; background: #fff; border-radius: 8px; border: 1px solid #eee; text-align: center;">
            <div style="font-size: 11px; color: #888;">{crypto_data[key]['name']}</div>
            <div style="font-size: 14px; font-weight: 800; color: {color};">{arrow} ₩{price_fmt}</div>
            <div style="font-size: 10px; color: {color};">({crypto_data[key]['chg']:.2f}%)</div>
        </div>"""
    
    return f"""
    <div style="font-family: -apple-system; margin-bottom: 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 15px;">
        <h3 style="text-align: center; margin: 0 0 10px 0; font-size: 16px; color: white;">🪙 Crypto Market Flow</h3>
        <div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 5px;">{items_html}</div>
    </div>"""

# =========================================================
# [함수 2] 암호화폐 뉴스 가져오기
# =========================================================
def get_crypto_news_list():
    print("🔍 암호화폐 뉴스 검색...")
    
    # 방법 1: 구글 뉴스에서 암호화폐 키워드 검색
    rss_url = "https://news.google.com/rss/search?q=암호화폐+OR+비트코인+OR+알트코인+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            print(f"✅ {len(feed.entries[:10])}개 뉴스 발견")
            return feed.entries[:10]  # 상위 10개
    except Exception as e:
        print(f"⛔ 뉴스 검색 에러: {e}")
    return []

# =========================================================
# [함수 3-6] 중복확인, 크롤링, 관련기사, AI분석
# =========================================================
def check_is_duplicate(service, news_title):
    try:
        posts = service.posts().list(blogId=BLOG_ID, maxResults=10).execute()
        for post in posts.get('items', []):
            if news_title in post.get('content', ''):
                return True
    except:
        pass
    return False

def fetch_article_content(url):
    print(f"📰 기사 크롤링...")
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False)
            if text and len(text) > 100:
                print(f"✅ {len(text)}자 추출")
                return text[:2500]
    except Exception as e:
        print(f"⚠️ 크롤링 실패: {e}")
    return None

def find_related_articles(target_title, all_news_list):
    print("🔍 비슷한 기사 찾기...")
    target_keywords = set(target_title.split())
    related = []
    
    for news in all_news_list:
        if news.title == target_title:
            continue
        if len(set(news.title.split()) & target_keywords) >= 2:
            related.append(news)
            if len(related) >= 3:
                break
    
    combined = ""
    for news in related:
        try:
            downloaded = trafilatura.fetch_url(news.link)
            if downloaded:
                text = trafilatura.extract(downloaded)
                if text:
                    combined += f"\n{text[:600]}\n"
                    if len(combined) > 1800:
                        break
        except:
            continue
    
    if combined:
        print(f"✅ {len(combined)}자 수집")
    return combined if combined else None

def ask_ai_about_crypto(news_title):
    print("🤖 AI 분석...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"'{news_title}' 암호화폐 뉴스를 4-5문단으로 분석: 배경, 블록체인 원리, 시장 영향, 향후 전망"
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text) > 150:
                print(f"✅ {len(text)}자 생성")
                return text[:2000]
    except:
        pass
    return None

# =========================================================
# [함수 7] 암호화폐 정보 리서치
# =========================================================
def research_crypto_coins(news_title, article_content):
    print("🔬 코인 리서치...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    context = article_content[:1000] if article_content else news_title
    
    prompt = f"""{context}

이 뉴스와 관련된 암호화폐 코인들을 찾아주세요:
1. 주요 코인 2-3개 (예: Bitcoin, Ethereum, Cardano)
2. 각 코인의 현재 시가총액 순위
3. 각 코인의 핵심 기술 특징

JSON으로 출력:
{{
  "coins": [
    {{"name": "Bitcoin", "symbol": "BTC", "tech": "작업증명", "rank": 1}},
    {{"name": "Ethereum", "symbol": "ETH", "tech": "스마트 컨트랙트", "rank": 2}}
  ]
}}"""
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=15)
        if res.status_code == 200:
            raw = res.json()['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                print(f"✅ 코인 정보 획득")
                return data
    except:
        pass
    return None

def get_coin_price_data(coin_symbols):
    """CoinGecko에서 실시간 코인 가격 정보"""
    print("💰 코인 가격 데이터 수집...")
    
    # 심볼 → CoinGecko ID 매핑
    symbol_to_id = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'BNB': 'binancecoin',
        'XRP': 'ripple',
        'ADA': 'cardano',
        'SOL': 'solana',
        'DOT': 'polkadot',
        'DOGE': 'dogecoin',
        'MATIC': 'matic-network',
        'LINK': 'chainlink'
    }
    
    coin_data = []
    
    for symbol in coin_symbols[:3]:  # 최대 3개
        symbol_upper = symbol.upper()
        coin_id = symbol_to_id.get(symbol_upper, symbol.lower())
        
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
            res = requests.get(url, timeout=10).json()
            
            coin_data.append({
                'name': res['name'],
                'symbol': res['symbol'].upper(),
                'price': f"₩{res['market_data']['current_price']['krw']:,.0f}",
                'market_cap': f"₩{res['market_data']['market_cap']['krw']/1e12:.2f}조",
                'change_24h': f"{res['market_data']['price_change_percentage_24h']:.2f}%",
                'rank': res['market_cap_rank']
            })
            print(f"  ✅ {res['name']}")
        except:
            continue
    
    return coin_data

def make_coin_cards(coin_data):
    if not coin_data:
        return ""
    
    cards = '<div style="display: flex; flex-wrap: wrap; gap: 15px; margin: 25px 0;">'
    for c in coin_data:
        change_color = "#d63031" if float(c['change_24h'].replace('%', '')) >= 0 else "#0984e3"
        
        cards += f"""
        <div style="flex: 1 1 calc(50% - 15px); min-width: 250px; background: linear-gradient(135deg, #667eea22 0%, #764ba233 100%); border-radius: 12px; padding: 20px; border-left: 4px solid #667eea;">
            <h3 style="margin: 0 0 10px 0;">{c['name']} ({c['symbol']})</h3>
            <p style="margin: 5px 0; font-size: 13px;"><b>순위:</b> #{c['rank']}</p>
            <p style="margin: 5px 0; font-size: 13px;"><b>현재가:</b> {c['price']}</p>
            <p style="margin: 5px 0; font-size: 13px;"><b>시총:</b> {c['market_cap']}</p>
            <p style="margin: 5px 0; font-size: 13px; color: {change_color};"><b>24h 변동:</b> {c['change_24h']}</p>
        </div>"""
    cards += '</div>'
    return cards

# =========================================================
# [함수 8-9] 키워드, 이미지
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"'{news_title}' 영어 키워드 2개만 콤마로"
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "cryptocurrency, blockchain"

def get_relevant_images_webp(query):
    if not PEXELS_API_KEY:
        return []
    try:
        resp = requests.get("https://api.pexels.com/v1/search", 
                          headers={"Authorization": PEXELS_API_KEY}, 
                          params={"query": query, "per_page": 2}, timeout=10)
        if resp.status_code == 200:
            return [p['src']['original']+"?auto=compress&fm=webp&w=800" for p in resp.json().get('photos', [])]
    except:
        pass
    return []

# =========================================================
# [함수 10] 마크다운 클리너
# =========================================================
def clean_markdown(text):
    text = re.sub(r'\*\*([^\*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^\*]+)\*', r'<em>\1</em>', text)
    text = text.replace('###', '').replace('##', '').replace('#', '')
    text = text.replace('```', '').replace('**', '').replace('__', '')
    text = re.sub(r'<i>(\d+)</i>', r'\1', text)
    text = re.sub(r'</i>', '', text)
    text = re.sub(r'<i>', '', text)
    return text

# =========================================================
# [함수 11] ★ 암호화폐 심층 칼럼 작성
# =========================================================
def generate_crypto_content(news, images, dashboard, article_content, coin_data):
    print("🧠 암호화폐 칼럼 작성...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    article_part = f"[기사 발췌]\n{article_content[:1200]}" if article_content else ""
    coin_summary = ""
    if coin_data:
        coin_summary = "\n[관련 코인]\n" + "\n".join([f"- {c['name']}({c['symbol']}): 순위 #{c['rank']}, {c['price']}" for c in coin_data])
    
    prompt = f"""
    암호화폐 전문 애널리스트로서 심층 분석 작성.
    
    [뉴스] {news.title}
    {article_part}
    {coin_summary}
    
    HTML 구조:
    DASHBOARDHERE
    <h2>🔥 [도발적 소제목]</h2>
    <p>[후킹: 돈/기회 자극 3문장]</p>
    IMAGE1HERE
    <h2>⛓️ 블록체인 원리</h2>
    <p>[기술 원리 설명 5문장]</p>
    <h2>🪙 주목할 코인들</h2>
    <p>[코인 분석 4문장]</p>
    COINCARDSHERE
    IMAGE2HERE
    <h2>📈 시장 전망과 기회</h2>
    <p>[투자 인사이트 4문장]</p>
    <h2>⚠️ 리스크 요인</h2>
    <p>[위험 요소 3문장]</p>
    <p><strong>결론:</strong> [1문장]</p>
    <hr><p style="color:grey; font-size:0.85em;">📰 출처: {news.title}<br>⚠️ 투자 판단은 본인 책임입니다.</p>
    
    규칙: HTML만 출력, 해요체, 각 섹션 3문장 이상
    """
    
    for attempt in range(3):
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            if res.status_code == 200:
                raw = res.json()['candidates'][0]['content']['parts'][0]['text']
                
                clean = clean_markdown(raw)
                clean = clean.replace("```html", "").replace("```", "").strip()
                
                # 치환
                clean = clean.replace("DASHBOARDHERE", dashboard)
                clean = clean.replace("[[DASHBOARD]]", dashboard)
                
                cards_html = make_coin_cards(coin_data)
                clean = clean.replace("COINCARDSHERE", cards_html)
                clean = clean.replace("[[COIN_CARDS]]", cards_html)
                clean = clean.replace("[[COINCARDS]]", cards_html)
                
                img1 = f'<img src="{images[0]}" style="width:100%; border-radius:12px; margin:25px 0;">' if len(images) > 0 else ""
                img2 = f'<img src="{images[1]}" style="width:100%; border-radius:12px; margin:25px 0;">' if len(images) > 1 else img1
                
                clean = clean.replace("IMAGE1HERE", img1)
                clean = clean.replace("IMAGE2HERE", img2)
                clean = clean.replace("[[IMAGE_1]]", img1)
                clean = clean.replace("[[IMAGE_2]]", img2)
                
                if len(clean) > 500:
                    print(f"✅ {len(clean)}자 완성")
                    return clean
                    
            time.sleep(3)
        except Exception as e:
            print(f"❌ 시도 {attempt+1}: {e}")
            time.sleep(5)
    return None

def generate_title(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"'{news_title}' 암호화폐 블로그 제목 1개만. 투자 기회 강조. 특수문자 금지."
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=10)
        title = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        return title.split('\n')[0].replace('"', '').replace('*', '').strip()
    except:
        return news_title

# =========================================================
# [메인 실행]
# =========================================================
def run_bot():
    print("▶️ 암호화폐 블로그 봇 시작")
    try:
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        news_list = get_crypto_news_list()
        if not news_list:
            print("❌ 뉴스 없음")
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

        # 3단계 폴백
        article_content = fetch_article_content(target.link)
        if not article_content:
            article_content = find_related_articles(target.title, news_list)
        if not article_content:
            article_content = ask_ai_about_crypto(target.title)
        
        # 코인 리서치
        research_data = research_crypto_coins(target.title, article_content)
        coin_data = []
        if research_data and 'coins' in research_data:
            symbols = [c['symbol'] for c in research_data['coins']]
            coin_data = get_coin_price_data(symbols)
        
        keywords = get_search_keywords(target.title)
        images = get_relevant_images_webp(keywords)
        dashboard = get_crypto_dashboard_html()
        
        content = generate_crypto_content(target, images, dashboard, article_content, coin_data)
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
