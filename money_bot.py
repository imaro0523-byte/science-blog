import os
import json
import time
import re
import requests
import feedparser
import yfinance as yf
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

MODEL_NAME = "gemini-3-flash-preview"

# =========================================================
# [함수 1] 시장 대시보드
# =========================================================
def get_dashboard_html():
    print("📊 시장 데이터 수집 중...")
    
    data = {
        "btc": {"price": 0, "chg": 0, "name": "비트코인"},
        "snp": {"price": 0, "chg": 0, "name": "S&P 500"},
        "nas": {"price": 0, "chg": 0, "name": "나스닥"},
        "kos": {"price": 0, "chg": 0, "name": "코스피"},
        "kdq": {"price": 0, "chg": 0, "name": "코스닥"}
    }

    tickers = {'^GSPC': 'snp', '^IXIC': 'nas', '^KS11': 'kos', '^KQ11': 'kdq'}
    try:
        for ticker, key in tickers.items():
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) >= 2:
                close_today = hist['Close'].iloc[-1]
                close_prev = hist['Close'].iloc[-2]
                data[key]['price'] = close_today
                data[key]['chg'] = ((close_today - close_prev) / close_prev) * 100
    except Exception as e:
        print(f"⚠️ 주식 데이터 실패: {e}")

    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=krw&include_24hr_change=true"
        res = requests.get(url, timeout=5).json()
        data['btc']['price'] = res['bitcoin']['krw']
        data['btc']['chg'] = res['bitcoin']['krw_24h_change']
    except:
        pass

    def get_style(chg):
        color = "#d63031" if chg >= 0 else "#0984e3"
        arrow = "▲" if chg >= 0 else "▼"
        return color, arrow

    items_html = ""
    for key in ['btc', 'snp', 'nas', 'kos', 'kdq']:
        color, arrow = get_style(data[key]['chg'])
        price_fmt = f"{data[key]['price']:,.0f}" if key == 'btc' else f"{data[key]['price']:,.2f}"
        
        items_html += f"""
        <div style="flex: 1 1 18%; min-width: 100px; margin: 5px; padding: 10px; background: #fff; border-radius: 8px; border: 1px solid #eee; text-align: center;">
            <div style="font-size: 11px; color: #888;">{data[key]['name']}</div>
            <div style="font-size: 14px; font-weight: 800; color: {color};">{arrow} {price_fmt}</div>
            <div style="font-size: 10px; color: {color};">({data[key]['chg']:.2f}%)</div>
        </div>"""
    
    return f"""
    <div style="font-family: -apple-system; margin-bottom: 30px; background: #f8f9fa; border-radius: 12px; padding: 15px;">
        <h3 style="text-align: center; margin: 0 0 10px 0; font-size: 16px;">⚡ Market Flow Check</h3>
        <div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 5px;">{items_html}</div>
    </div>"""

# =========================================================
# [함수 2-6] 뉴스, 중복확인, 크롤링, 관련기사, AI분석
# =========================================================
def get_business_news_list():
    print("🔍 금융 뉴스 검색...")
    try:
        feed = feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko")
        if feed.entries:
            return feed.entries[:5]
    except:
        pass
    return []

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

def ask_ai_about_economy(news_title):
    print("🤖 AI 분석...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"'{news_title}' 경제 뉴스를 4-5문단으로 분석: 배경, 경제 원리, 영향, 전망"
    
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
# [함수 7] 기업 리서치
# =========================================================
def research_companies(news_title, article_content):
    print("🔬 기업 리서치...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    context = article_content[:1000] if article_content else news_title
    
    prompt = f"{context}\n\n미국 기업 1-2개(티커), 한국 기업 1-2개(티커) JSON 출력:\n{{'us_companies':['Apple(AAPL)'],'kr_companies':['삼성전자(005930.KS)']}}"
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=15)
        if res.status_code == 200:
            raw = res.json()['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                print(f"✅ 기업 발견")
                return data
    except:
        pass
    return None

def get_company_info(companies_list):
    print("💼 기업 정보 수집...")
    results = []
    
    for company_str in companies_list:
        try:
            ticker_match = re.search(r'\(([^)]+)\)', company_str)
            if not ticker_match:
                continue
            
            ticker = ticker_match.group(1)
            name = company_str.split('(')[0].strip()
            stock = yf.Ticker(ticker)
            info = stock.info
            
            market_cap = info.get('marketCap', 0)
            if market_cap:
                cap_display = f"{market_cap/1e12:.1f}조원" if 'KS' in ticker else f"${market_cap/1e9:.1f}B"
            else:
                cap_display = "N/A"
            
            price = info.get('currentPrice', 0)
            if not price:
                hist = stock.history(period="1d")
                price = hist['Close'].iloc[-1] if len(hist) > 0 else 0
            
            results.append({
                'name': name,
                'ticker': ticker,
                'price': f"${price:.2f}" if price else "N/A",
                'market_cap': cap_display,
                'sector': info.get('sector', 'N/A')
            })
            print(f"  ✅ {name}")
        except:
            continue
    
    return results

def make_company_cards(company_data):
    if not company_data:
        return ""
    
    cards = '<div style="display: flex; flex-wrap: wrap; gap: 15px; margin: 25px 0;">'
    for c in company_data:
        cards += f"""
        <div style="flex: 1 1 calc(50% - 15px); min-width: 250px; background: #f8f9fa; border-radius: 12px; padding: 20px; border-left: 4px solid #0984e3;">
            <h3 style="margin: 0 0 10px 0;">{c['name']}</h3>
            <p style="margin: 5px 0; font-size: 13px;"><b>티커:</b> {c['ticker']}</p>
            <p style="margin: 5px 0; font-size: 13px;"><b>현재가:</b> {c['price']}</p>
            <p style="margin: 5px 0; font-size: 13px;"><b>시총:</b> {c['market_cap']}</p>
            <p style="margin: 5px 0; font-size: 13px;"><b>섹터:</b> {c['sector']}</p>
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
        return "business, economy"

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
# [함수 10] 마크다운 클리너 (강화!)
# =========================================================
def clean_markdown(text):
    # **bold** → <b>bold</b>
    text = re.sub(r'\*\*([^\*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^\*]+)\*', r'<em>\1</em>', text)
    # 남은 마크다운 제거
    text = text.replace('###', '').replace('##', '').replace('#', '')
    text = text.replace('```', '').replace('**', '').replace('__', '')
    # HTML 태그 정리
    text = re.sub(r'<i>(\d+)</i>', r'\1', text)  # <i>1</i> → 1
    text = re.sub(r'</i>', '', text)
    text = re.sub(r'<i>', '', text)
    return text

# =========================================================
# [함수 11] ★ 본문 생성 (치환 문제 해결!)
# =========================================================
def generate_content(news, images, dashboard, article_content, company_data):
    print("🧠 칼럼 작성...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    article_part = f"[기사 발췌]\n{article_content[:1200]}" if article_content else ""
    company_summary = ""
    if company_data:
        company_summary = "\n[관련 기업]\n" + "\n".join([f"- {c['name']}: {c['market_cap']}, {c['sector']}" for c in company_data])
    
    prompt = f"""
    경제 전문 칼럼니스트로서 심층 분석 작성.
    
    [뉴스] {news.title}
    {article_part}
    {company_summary}
    
    HTML 구조:
    DASHBOARDHERE
    <h2>🔥 소제목</h2>
    <p>후킹 3문장</p>
    IMAGE1HERE
    <h2>📚 경제 원리</h2>
    <p>설명 5문장</p>
    <h2>🏢 관련 기업</h2>
    <p>기업 분석 4문장</p>
    COMPANYCARDSHERE
    IMAGE2HERE
    <h2>💰 인사이트</h2>
    <p>전망 4문장</p>
    <p><strong>결론:</strong> 1문장</p>
    <hr><p style="color:grey; font-size:0.85em;">📰 출처: {news.title}</p>
    
    규칙: HTML만 출력, 해요체, 각 섹션 3문장 이상
    """
    
    for attempt in range(3):
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
            if res.status_code == 200:
                raw = res.json()['candidates'][0]['content']['parts'][0]['text']
                
                # ★ 1단계: 마크다운 클리닝
                clean = clean_markdown(raw)
                clean = clean.replace("```html", "").replace("```", "").strip()
                
                # ★ 2단계: 대시보드 치환
                clean = clean.replace("DASHBOARDHERE", dashboard)
                clean = clean.replace("[[DASHBOARD]]", dashboard)
                
                # ★ 3단계: 기업 카드 치환
                cards_html = make_company_cards(company_data)
                clean = clean.replace("COMPANYCARDSHERE", cards_html)
                clean = clean.replace("[[COMPANY_CARDS]]", cards_html)
                clean = clean.replace("[[COMPANYCARDS]]", cards_html)
                
                # ★ 4단계: 이미지 치환
                img1 = f'<img src="{images[0]}" style="width:100%; border-radius:12px; margin:25px 0;">' if len(images) > 0 else ""
                img2 = f'<img src="{images[1]}" style="width:100%; border-radius:12px; margin:25px 0;">' if len(images) > 1 else img1
                
                clean = clean.replace("IMAGE1HERE", img1)
                clean = clean.replace("IMAGE2HERE", img2)
                clean = clean.replace("[[IMAGE_1]]", img1)
                clean = clean.replace("[[IMAGE_2]]", img2)
                clean = clean.replace("[[IMAGE1]]", img1)
                clean = clean.replace("[[IMAGE2]]", img2)
                
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
    prompt = f"'{news_title}' 블로그 제목 1개만. 도파민 자극. 특수문자 금지."
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
    print("▶️ 경제 블로그 봇 시작")
    try:
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        news_list = get_business_news_list()
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

        # 3단계 폴백
        article_content = fetch_article_content(target.link)
        if not article_content:
            article_content = find_related_articles(target.title, news_list)
        if not article_content:
            article_content = ask_ai_about_economy(target.title)
        
        research_data = research_companies(target.title, article_content)
        company_data = []
        if research_data:
            all_companies = research_data.get('us_companies', []) + research_data.get('kr_companies', [])
            company_data = get_company_info(all_companies)
        
        keywords = get_search_keywords(target.title)
        images = get_relevant_images_webp(keywords)
        dashboard = get_dashboard_html()
        
        content = generate_content(target, images, dashboard, article_content, company_data)
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
