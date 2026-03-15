import os
import json
import time
import re
import requests
import feedparser
import trafilatura
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# 설정
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')
BLOG_ID = os.environ.get('CRYPTO_BLOG_ID') or os.environ.get('BLOG_ID')

if not GEMINI_API_KEY or not BLOG_ID:
    exit(1)

try:
    CLIENT_JSON = json.loads(os.environ.get('CLIENT_JSON', '{}'))
    TOKEN_JSON = json.loads(os.environ.get('TOKEN_JSON', '{}'))
except:
    exit(1)

MODEL_NAME = "gemini-2.5-flash"

# 대시보드
def get_crypto_dashboard_html():
    data = {}
    try:
        res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,binancecoin,ripple,cardano&vs_currencies=krw&include_24hr_change=true", timeout=10).json()
        data = {
            "btc": {"price": res.get('bitcoin', {}).get('krw', 0), "chg": res.get('bitcoin', {}).get('krw_24h_change', 0), "name": "비트코인"},
            "eth": {"price": res.get('ethereum', {}).get('krw', 0), "chg": res.get('ethereum', {}).get('krw_24h_change', 0), "name": "이더리움"},
            "bnb": {"price": res.get('binancecoin', {}).get('krw', 0), "chg": res.get('binancecoin', {}).get('krw_24h_change', 0), "name": "바이낸스"},
            "xrp": {"price": res.get('ripple', {}).get('krw', 0), "chg": res.get('ripple', {}).get('krw_24h_change', 0), "name": "리플"},
            "ada": {"price": res.get('cardano', {}).get('krw', 0), "chg": res.get('cardano', {}).get('krw_24h_change', 0), "name": "카르다노"}
        }
    except:
        for key in ['btc', 'eth', 'bnb', 'xrp', 'ada']:
            data[key] = {"price": 0, "chg": 0, "name": key.upper()}
    
    items = ""
    for key in ['btc', 'eth', 'bnb', 'xrp', 'ada']:
        color, arrow = ("#d63031", "▲") if data[key]['chg'] >= 0 else ("#0984e3", "▼")
        items += f'<div style="flex:1 1 18%;min-width:100px;margin:5px;padding:10px;background:#fff;border-radius:8px;text-align:center;"><div style="font-size:11px;color:#888;">{data[key]["name"]}</div><div style="font-size:14px;font-weight:800;color:{color};">{arrow} ₩{data[key]["price"]:,.0f}</div><div style="font-size:10px;color:{color};">({data[key]["chg"]:.2f}%)</div></div>'
    return f'<div style="margin-bottom:30px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);border-radius:12px;padding:15px;"><h3 style="text-align:center;margin:0 0 10px 0;font-size:16px;color:white;">🪙 암호화폐 시장</h3><div style="display:flex;flex-wrap:wrap;justify-content:center;gap:5px;">{items}</div></div>'

# 뉴스 (더 많이 가져오기)
def get_crypto_news_list():
    print("🔍 암호화폐 뉴스 검색...")
    try:
        feed = feedparser.parse("https://news.google.com/rss/search?q=암호화폐+OR+비트코인+OR+알트코인+OR+블록체인+when:1d&hl=ko&gl=KR")
        if feed.entries:
            print(f"✅ {len(feed.entries[:12])}개 뉴스 발견")
            return feed.entries[:12]  # ★ 12개로 증가
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
    try:
        text = trafilatura.extract(trafilatura.fetch_url(url))
        if text and len(text) > 100:
            print(f"✅ {len(text)}자 추출")
            return text[:3000]
    except:
        pass
    return None

# ★ 경제 블로그처럼 여러 출처 수집
def collect_multiple_sources(target_news, all_news_list):
    print("📰 여러 출처에서 정보 수집 중...")
    sources = []
    target_keywords = set(target_news.title.split())
    
    # 1. 타겟 기사
    content1 = fetch_article_content(target_news.link)
    if content1:
        sources.append({'title': target_news.title, 'content': content1, 'link': target_news.link})
    
    # 2. 비슷한 기사 3-4개 더
    for news in all_news_list:
        if news.title != target_news.title and len(set(news.title.split()) & target_keywords) >= 2:
            content = fetch_article_content(news.link)
            if content:
                sources.append({'title': news.title, 'content': content, 'link': news.link})
                if len(sources) >= 4:
                    break
    
    print(f"✅ {len(sources)}개 출처 수집 완료")
    return sources

# ★ 종합 분석
def synthesize_sources(sources):
    print("🧠 여러 출처 종합 분석...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    sources_text = "\n".join([f"[출처{i+1}]{s['title']}\n{s['content'][:800]}" for i, s in enumerate(sources)])
    
    prompt = f"""
    여러 암호화폐 뉴스를 종합 분석하세요.
    
    {sources_text}
    
    다음 분석:
    1. 공통적으로 언급된 핵심 사실
    2. 출처마다 다르게 해석한 부분
    3. 기사에서 다루지 않은 숨겨진 맥락
    4. 암호화폐 전문가 관점에서의 해석
    5. 투자자/트레이더에게 미치는 영향
    
    1500자 이상, 5-6문단으로 작성.
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text) > 200:
                print(f"✅ {len(text)}자 종합 분석 완료")
                return text[:3000]
    except:
        pass
    return None

# ★ 심층 리서치 (대폭 강화!)
def research_crypto_deeply(news_title, synthesized):
    print("🔬 암호화폐 심층 리서치 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    context = synthesized[:1500] if synthesized else news_title
    
    prompt = f"""
    {context}
    
    다음 항목을 각 4-5문장으로 상세히 분석:
    
    1. blockchain_tech: 관련 블록체인 기술 (PoW/PoS, Layer2, DeFi, NFT 등 구체적 기술)
    2. crypto_history: 암호화폐 역사적 맥락 (비트코인 반감기, Mt.Gox, DeFi 붐, NFT 광풍 등 과거 사례)
    3. regulation: 각국 규제 환경 (미국 SEC, 한국 특금법, 중국 금지령 등)
    4. market_sentiment: 시장 심리 (Fear & Greed Index, 온체인 지표, 고래 움직임)
    5. trending_coins: 최근 화제의 코인 (해외 트렌딩 코인, SNS에서 화제)
    6. new_technology: 새로운 블록체인 기술 트렌드 (ZK-Rollup, Modular blockchain 등)
    7. future_outlook: 미래 전망 (3-5년 후 DeFi, Web3, 메타버스 응용)
    8. investment_risk: 투자 리스크 (변동성, 규제, 보안, 러그풀)
    
    JSON 출력:
    {{"blockchain_tech":"...","crypto_history":"...","regulation":"...","market_sentiment":"...","trending_coins":"...","new_technology":"...","future_outlook":"...","investment_risk":"..."}}
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        if res.status_code == 200:
            match = re.search(r'\{.*\}', res.json()['candidates'][0]['content']['parts'][0]['text'], re.DOTALL)
            if match:
                data = json.loads(match.group())
                print("✅ 심층 리서치 완료")
                return data
    except:
        pass
    return None

# ★ 백서 및 커뮤니티 평판 분석 (신규!)
def analyze_whitepaper_and_community(news_title, synthesized, research_data):
    print("📄 백서 & 커뮤니티 평판 분석...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    trending_coins = research_data.get('trending_coins', '') if research_data else ''
    
    prompt = f"""
    다음 암호화폐 뉴스와 관련하여 백서 및 커뮤니티 평판을 분석하세요.
    
    [뉴스] {news_title}
    [종합 분석] {synthesized[:1000] if synthesized else ''}
    [화제 코인] {trending_coins}
    
    다음을 각 3-4문장으로:
    
    1. whitepaper_summary: 관련 코인의 백서 핵심 내용 (기술적 목표, 차별점, 토크노믹스)
    2. reddit_sentiment: Reddit r/cryptocurrency, r/bitcoin 등에서의 평판 (긍정/부정/중립, 주요 논의)
    3. twitter_buzz: Twitter/X에서의 화제성 (인플루언서 의견, 트렌딩 여부)
    4. github_activity: GitHub 개발 활동 (커밋 빈도, 개발자 수, 코드 품질 - 알려진 정보 기반)
    5. competitor_comparison: 경쟁 코인 대비 장단점
    
    JSON 출력:
    {{"whitepaper_summary":"...","reddit_sentiment":"...","twitter_buzz":"...","github_activity":"...","competitor_comparison":"..."}}
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=25)
        if res.status_code == 200:
            match = re.search(r'\{.*\}', res.json()['candidates'][0]['content']['parts'][0]['text'], re.DOTALL)
            if match:
                data = json.loads(match.group())
                print("✅ 백서/커뮤니티 분석 완료")
                return data
    except:
        pass
    return None

# 코인 정보
def research_crypto_coins(synthesized):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": f"{synthesized[:1000]}\n\n관련 코인 2-3개 JSON:{{'coins':[{{'name':'Bitcoin','symbol':'BTC'}}]}}"}]}]}, timeout=15)
        if res.status_code == 200:
            match = re.search(r'\{.*\}', res.json()['candidates'][0]['content']['parts'][0]['text'], re.DOTALL)
            if match:
                return json.loads(match.group())
    except:
        pass
    return None

def get_coin_price_data(symbols):
    symbol_to_id = {'BTC': 'bitcoin', 'ETH': 'ethereum', 'BNB': 'binancecoin', 'XRP': 'ripple', 'ADA': 'cardano', 'SOL': 'solana', 'DOT': 'polkadot', 'DOGE': 'dogecoin', 'MATIC': 'matic-network', 'LINK': 'chainlink', 'AVAX': 'avalanche-2', 'UNI': 'uniswap'}
    coin_data = []
    for symbol in symbols[:3]:
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
            print(f"  ✅ {res['name']}")
        except:
            continue
    return coin_data

def make_coin_cards(coin_data):
    if not coin_data:
        return ""
    cards = '<div style="display:flex;flex-wrap:wrap;gap:15px;margin:25px 0;">'
    for c in coin_data:
        color = "#d63031" if float(c['change_24h'].replace('%', '')) >= 0 else "#0984e3"
        cards += f'<div style="flex:1 1 calc(50%-15px);min-width:250px;background:linear-gradient(135deg,#667eea22,#764ba233);border-radius:12px;padding:20px;border-left:4px solid #667eea;"><h3 style="margin:0 0 10px 0;">{c["name"]}({c["symbol"]})</h3><p style="margin:5px 0;font-size:13px;"><b>순위:</b>#{c["rank"]}</p><p style="margin:5px 0;font-size:13px;"><b>현재가:</b>{c["price"]}</p><p style="margin:5px 0;font-size:13px;"><b>시총:</b>{c["market_cap"]}</p><p style="margin:5px 0;font-size:13px;color:{color};"><b>24h:</b>{c["change_24h"]}</p></div>'
    cards += '</div>'
    return cards

# 키워드, 이미지
def get_search_keywords(news_title):
    try:
        res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}", json={"contents": [{"parts": [{"text": f"'{news_title}' 영어 키워드 2개"}]}]}, timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "cryptocurrency, blockchain"

def get_relevant_images_webp(query):
    if not PEXELS_API_KEY:
        return []
    try:
        resp = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": PEXELS_API_KEY}, params={"query": query, "per_page": 2}, timeout=10)
        if resp.status_code == 200:
            return [p['src']['original'] + "?w=800" for p in resp.json().get('photos', [])]
    except:
        pass
    return []

def clean_markdown(text):
    text = re.sub(r'\*\*([^\*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^\*]+)\*', r'<em>\1</em>', text)
    text = text.replace('###', '').replace('##', '').replace('```', '').replace('**', '')
    text = re.sub(r'<i>(\d+)</i>', r'\1', text)
    return re.sub(r'</i>|<i>', '', text)

# ★ 초장문 칼럼 (경제 블로그 수준)
def generate_premium_crypto_content(news, images, dashboard, sources, synthesized, research_data, whitepaper_data, coin_data):
    print("🧠 프리미엄 암호화폐 칼럼 작성...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    sources_ref = ""
    if sources:
        sources_ref = "\n[참고 출처]\n" + "\n".join([f"{i+1}. {s['title']}" for i, s in enumerate(sources)])
    
    analysis_part = f"\n[종합 분석]\n{synthesized[:1500]}\n" if synthesized else ""
    
    research_section = ""
    if research_data:
        research_section = f"""
[암호화폐 전문 지식]
- 블록체인 기술: {research_data.get('blockchain_tech', 'N/A')}
- 역사: {research_data.get('crypto_history', 'N/A')}
- 규제: {research_data.get('regulation', 'N/A')}
- 시장 심리: {research_data.get('market_sentiment', 'N/A')}
- 화제 코인: {research_data.get('trending_coins', 'N/A')}
- 신기술: {research_data.get('new_technology', 'N/A')}
- 미래: {research_data.get('future_outlook', 'N/A')}
- 리스크: {research_data.get('investment_risk', 'N/A')}
"""
    
    whitepaper_section = ""
    if whitepaper_data:
        whitepaper_section = f"""
[백서 & 커뮤니티]
- 백서 요약: {whitepaper_data.get('whitepaper_summary', 'N/A')}
- Reddit 평판: {whitepaper_data.get('reddit_sentiment', 'N/A')}
- Twitter 화제성: {whitepaper_data.get('twitter_buzz', 'N/A')}
- GitHub 활동: {whitepaper_data.get('github_activity', 'N/A')}
- 경쟁 분석: {whitepaper_data.get('competitor_comparison', 'N/A')}
"""
    
    coin_summary = ""
    if coin_data:
        coin_summary = "\n[관련 코인]\n" + "\n".join([f"- {c['name']}({c['symbol']}): #{c['rank']}, {c['price']}" for c in coin_data])
    
    prompt = f"""
    암호화폐 전문 애널리스트로 **완전 독창적 심층 칼럼** 작성.
    
    [주제] {news.title}
    {sources_ref}
    {analysis_part}
    {research_section}
    {whitepaper_section}
    {coin_summary}
    
    [애드센스 승인 필수]
    1. 독창성: 단순 뉴스 요약 절대 금지, 전문가 재해석
    2. 길이: 2500자 이상
    3. 부가가치: 백서 분석, 커뮤니티 평판, 신기술 트렌드
    4. 다각도: 찬반 양론, 투자자/개발자 관점
    5. 실용성: 투자 판단에 도움
    6. 출처: 투명하게 명시
    
    HTML:
    DASHBOARDHERE
    <div style="background:#fff3cd;padding:15px;border-left:4px solid #ffc107;margin:20px 0;">
    <strong>📌 편집자 주</strong><p>{len(sources)}개 출처 교차 분석 + 백서 리뷰 + 커뮤니티 평판 조사를 통한 독창적 칼럼</p>
    </div>
    <h2>🔥 [투자자 시선을 끄는 소제목]</h2>
    <p>[이 뉴스가 왜 중요한지 - 5문장 후킹]</p>
    IMAGE1HERE
    <h2>📊 팩트 체크</h2>
    <p>[여러 출처 공통 사실 - 6문장]</p>
    <ul><li>팩트 1</li><li>팩트 2</li><li>팩트 3</li></ul>
    <h2>⛓️ 블록체인 기술 해부</h2>
    <p>[기술 원리 상세 - 8문장]</p>
    <h2>📖 암호화폐 역사 속에서</h2>
    <p>[과거 비슷한 사례 2개 이상 - 7문장]</p>
    IMAGE2HERE
    <h2>⚖️ 각국 규제 현황</h2>
    <p>[미국/한국/중국 등 - 7문장]</p>
    <h2>🔥 지금 화제의 코인들</h2>
    <p>[해외 트렌딩 코인, SNS 화제 - 5문장]</p>
    COINCARDSHERE
    <h2>📄 백서로 보는 기술력</h2>
    <p>[백서 핵심 내용, 토크노믹스 - 6문장]</p>
    <h2>💬 커뮤니티는 뭐라고 할까</h2>
    <p>[Reddit/Twitter 평판 - 5문장]</p>
    <h2>🆕 최신 블록체인 기술 트렌드</h2>
    <p>[ZK-Rollup, Modular 등 - 6문장]</p>
    <h2>⚖️ 찬성 vs 반대</h2>
    <p><strong>찬성 입장:</strong> [3문장]</p>
    <p><strong>반대 입장:</strong> [3문장]</p>
    <p><strong>제 분석:</strong> [2문장]</p>
    <h2>💰 투자자에게 미치는 영향</h2>
    <p>[단기/중기/장기 투자자별 - 6문장]</p>
    <h2>🔮 3년 후 시나리오</h2>
    <p><strong>낙관:</strong> [2문장]</p>
    <p><strong>비관:</strong> [2문장]</p>
    <p><strong>현실:</strong> [2문장]</p>
    <h2>⚠️ 투자 리스크</h2>
    <p>[변동성, 규제, 보안, 러그풀 - 5문장]</p>
    <p><strong>결론:</strong> [3문장]</p>
    <hr>
    <div style="background:#f8f9fa;padding:15px;border-radius:8px;">
    <p><strong>📰 참고 출처</strong></p>
    {sources_ref.replace('[참고 출처]', '').strip()}
    <p style="font-size:12px;color:#999;">본 칼럼은 독립 분석이며 투자 권유 아님. DYOR(Do Your Own Research)</p>
    </div>
    
    규칙: HTML만, 해요체, 각 섹션 5문장 이상
    """
    
    for attempt in range(3):
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=50)
            if res.status_code == 200:
                clean = clean_markdown(res.json()['candidates'][0]['content']['parts'][0]['text']).replace("```html", "").replace("```", "").strip()
                clean = clean.replace("DASHBOARDHERE", dashboard).replace("[[DASHBOARD]]", dashboard)
                clean = clean.replace("COINCARDSHERE", make_coin_cards(coin_data)).replace("[[COIN_CARDS]]", make_coin_cards(coin_data))
                img1 = f'<img src="{images[0]}" style="width:100%;border-radius:12px;margin:25px 0;">' if len(images) > 0 else ""
                img2 = f'<img src="{images[1]}" style="width:100%;border-radius:12px;margin:25px 0;">' if len(images) > 1 else img1
                clean = clean.replace("IMAGE1HERE", img1).replace("IMAGE2HERE", img2).replace("[[IMAGE_1]]", img1).replace("[[IMAGE_2]]", img2)
                if len(clean) > 2000:
                    print(f"✅ {len(clean)}자 완성")
                    return clean
            time.sleep(3)
        except Exception as e:
            print(f"❌ {attempt+1}/3: {e}")
            time.sleep(5)
    return None

def generate_title(news_title):
    try:
        res = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}", json={"contents": [{"parts": [{"text": f"'{news_title}' 암호화폐 전문가 칼럼 제목 1개. 투자자 시선 사로잡기."}]}]}, timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')[0].replace('"', '').replace('*', '')
    except:
        return news_title

# 메인
def run_bot():
    print("▶️ 프리미엄 암호화폐 블로그 봇 (경제 수준)")
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

        # ★ 경제 블로그 수준 파이프라인
        # 1. 여러 출처 수집
        sources = collect_multiple_sources(target, news_list)
        
        # 2. 종합 분석
        synthesized = synthesize_sources(sources) if sources else None
        
        # 3. 심층 리서치
        research_data = research_crypto_deeply(target.title, synthesized)
        
        # 4. ★ 백서 & 커뮤니티 분석 (신규!)
        whitepaper_data = analyze_whitepaper_and_community(target.title, synthesized, research_data)
        
        # 5. 코인 정보
        coin_research = research_crypto_coins(synthesized) if synthesized else None
        coin_data = []
        if coin_research and 'coins' in coin_research:
            coin_data = get_coin_price_data([c['symbol'] for c in coin_research['coins']])
        
        # 6. 이미지, 대시보드
        keywords = get_search_keywords(target.title)
        images = get_relevant_images_webp(keywords)
        dashboard = get_crypto_dashboard_html()
        
        # 7. ★ 프리미엄 칼럼 작성
        content = generate_premium_crypto_content(target, images, dashboard, sources, synthesized, research_data, whitepaper_data, coin_data)
        if not content:
            print("❌ 작성 실패")
            return

        title = generate_title(target.title)
        print(f"\n📤 제목: {title}")
        print(f"📏 글자수: {len(content)}자")
        
        body = {"kind": "blogger#post", "title": title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"🎉 완료!")

    except Exception as e:
        print(f"⛔ 오류: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    run_bot()
