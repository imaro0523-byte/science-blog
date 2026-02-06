import os
import json
import time
import re
import requests
import feedparser
import yfinance as yf
import trafilatura  # ★ 추가 필요
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# =========================================================
# [설정 구역]
# =========================================================
print("🔧 환경변수 및 라이브러리 점검...")

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')
BLOG_ID = os.environ.get('BLOG_ID') 

if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY 누락")
    exit(1)
if not BLOG_ID:
    print("❌ BLOG_ID 누락")
    exit(1)

print(f"✅ 타겟 블로그 ID: {BLOG_ID[:5]}*****")

try:
    CLIENT_JSON = json.loads(os.environ.get('CLIENT_JSON', '{}'))
    TOKEN_JSON = json.loads(os.environ.get('TOKEN_JSON', '{}'))
except:
    print("⛔ 인증 토큰 로딩 실패")
    exit(1)

MODEL_NAME = "gemini-2.5-flash"  # ★ 모델명 수정

# =========================================================
# [함수 1] 통합 시장 대시보드
# =========================================================
def get_dashboard_html():
    print("📊 5대 핵심 자산 데이터 수집 중...")
    
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
        print(f"⚠️ 주식 데이터 수집 실패: {e}")

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
    display_order = ['btc', 'snp', 'nas', 'kos', 'kdq']
    
    for key in display_order:
        color, arrow = get_style(data[key]['chg'])
        price_fmt = f"{data[key]['price']:,.0f}" if key == 'btc' else f"{data[key]['price']:,.2f}"
        
        items_html += f"""
        <div style="flex: 1 1 18%; min-width: 100px; margin: 5px; padding: 10px; background: #ffffff; border-radius: 8px; border: 1px solid #eee; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.03);">
            <div style="font-size: 11px; color: #888; margin-bottom: 4px;">{data[key]['name']}</div>
            <div style="font-size: 14px; font-weight: 800; color: {color}; margin-bottom: 2px;">
                {arrow} {price_fmt}
            </div>
            <div style="font-size: 10px; color: {color}; font-weight: 500;">({data[key]['chg']:.2f}%)</div>
        </div>
        """
    
    full_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin-bottom: 30px; background: #f8f9fa; border-radius: 12px; padding: 15px;">
        <h3 style="text-align: center; margin: 0 0 10px 0; font-size: 16px; color: #2d3436; letter-spacing: -0.5px;">⚡ Market Flow Check</h3>
        <div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 5px;">
            {items_html}
        </div>
    </div>
    """
    return full_html

# =========================================================
# [함수 2] 뉴스 가져오기
# =========================================================
def get_business_news_list():
    print("🔍 구글 뉴스 [금융] 섹션 검색...")
    rss_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            return feed.entries[:5]
    except:
        pass
    return []

# =========================================================
# [함수 3] 중복 확인
# =========================================================
def check_is_duplicate(service, news_title):
    try:
        posts = service.posts().list(blogId=BLOG_ID, maxResults=10).execute()
        for post in posts.get('items', []):
            if news_title in post.get('content', ''): 
                return True
        return False
    except:
        return False

# =========================================================
# [함수 4] ★ 원문 크롤링 (핵심 추가!)
# =========================================================
def fetch_article_content(url):
    """뉴스 원문을 크롤링하여 본문 텍스트 추출"""
    print(f"📰 기사 본문 가져오는 중...")
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False)
            if text and len(text) > 100:
                print(f"✅ 본문 {len(text)}자 추출 성공")
                return text[:2000]
        print("⚠️ 본문 추출 실패")
        return None
    except Exception as e:
        print(f"⛔ 크롤링 에러: {e}")
        return None

# =========================================================
# [함수 4-1] ★ 비슷한 기사 여러 개 찾기 (크롤링 실패 시 대안)
# =========================================================
def find_related_articles(target_title, all_news_list):
    """같은 주제의 다른 기사들 찾아서 크롤링 시도"""
    print(f"🔍 비슷한 기사 찾는 중...")
    
    # 타겟 제목에서 핵심 키워드 추출 (간단하게 명사만)
    target_keywords = set(target_title.split())
    
    related_articles = []
    
    for news in all_news_list:
        if news.title == target_title:
            continue  # 자기 자신은 제외
        
        # 제목 유사도 계산 (공통 단어 개수)
        news_keywords = set(news.title.split())
        common = target_keywords & news_keywords
        
        if len(common) >= 2:  # 공통 단어 2개 이상이면 관련 기사
            related_articles.append(news)
            if len(related_articles) >= 3:  # 최대 3개까지
                break
    
    print(f"✅ 비슷한 기사 {len(related_articles)}개 발견")
    
    # 관련 기사들 크롤링 시도
    combined_content = ""
    for news in related_articles:
        try:
            downloaded = trafilatura.fetch_url(news.link)
            if downloaded:
                text = trafilatura.extract(downloaded, include_comments=False)
                if text and len(text) > 100:
                    combined_content += f"\n[관련 기사: {news.title[:50]}...]\n{text[:500]}\n"
                    print(f"  ✅ 추가 기사 크롤링 성공")
                    
                    if len(combined_content) > 1500:
                        break  # 충분히 수집
        except:
            continue
    
    if combined_content:
        print(f"✅ 총 {len(combined_content)}자 수집 완료")
        return combined_content
    
    return None

# =========================================================
# [함수 4-2] ★ AI에게 웹에서 정보 수집 요청 (최후 수단)
# =========================================================
def ask_ai_about_news(news_title):
    """AI가 학습한 지식으로 뉴스 분석"""
    print(f"🤖 AI 지식 기반으로 분석 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    다음 경제 뉴스에 대해 분석해주세요:
    "{news_title}"
    
    다음 정보를 포함해서 3-4문단으로 설명해주세요:
    1. 이 뉴스의 배경과 맥락
    2. 관련된 경제 원리나 시장 메커니즘
    3. 영향을 받을 것으로 예상되는 산업이나 기업
    4. 시장에 미칠 영향 예측
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, 
                          headers={'Content-Type': 'application/json'}, timeout=15)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text) > 100:
                print(f"✅ AI 분석 {len(text)}자 생성")
                return text[:1500]
    except Exception as e:
        print(f"⚠️ AI 분석 실패: {e}")
    
    return None

# =========================================================
# [함수 5] ★ 관련 기업 리서치 (핵심 추가!)
# =========================================================
def research_companies(news_title, article_content):
    """AI가 관련 기업 찾기"""
    print("🔬 관련 기업 리서치 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    context = f"기사: {article_content[:1000]}" if article_content else f"제목: {news_title}"
    
    prompt = f"""
    {context}
    
    이 뉴스와 관련된 기업을 찾아줘:
    1. 미국 기업 1-2개 (티커 포함, 예: Apple(AAPL))
    2. 한국 기업 1-2개 (티커 포함, 예: 삼성전자(005930.KS))
    
    JSON으로만 출력:
    {{
      "us_companies": ["Apple(AAPL)"],
      "kr_companies": ["삼성전자(005930.KS)"]
    }}
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'}, timeout=10)
        if res.status_code == 200:
            raw = res.json()['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                print(f"✅ 기업 발견: {len(data.get('us_companies', []))}개(미국), {len(data.get('kr_companies', []))}개(한국)")
                return data
    except Exception as e:
        print(f"⚠️ 리서치 실패: {e}")
    return None

# =========================================================
# [함수 6] ★ 기업 재무 정보 (핵심 추가!)
# =========================================================
def get_company_info(companies_list):
    """yfinance로 기업 정보 가져오기"""
    print("💼 기업 재무 정보 수집 중...")
    results = []
    
    for company_str in companies_list:
        try:
            ticker_match = re.search(r'\(([^)]+)\)', company_str)
            if not ticker_match:
                continue
            
            ticker = ticker_match.group(1)
            name = company_str.split('(')[0].strip()
            
            print(f"  📈 {name} ({ticker}) 조회 중...")
            stock = yf.Ticker(ticker)
            info = stock.info
            
            market_cap = info.get('marketCap', 0)
            if market_cap:
                if 'KS' in ticker:
                    cap_display = f"{market_cap / 1_000_000_000_000:.1f}조원"
                else:
                    cap_display = f"${market_cap / 1_000_000_000:.1f}B"
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
            
            print(f"  ✅ {name}: {cap_display}")
            
        except Exception as e:
            print(f"  ⚠️ {company_str} 실패: {e}")
            continue
    
    return results

# =========================================================
# [함수 7] 기업 카드 HTML
# =========================================================
def make_company_cards(company_data):
    if not company_data:
        return ""
    
    cards = '<div style="display: flex; flex-wrap: wrap; gap: 15px; margin: 25px 0;">'
    for c in company_data:
        cards += f"""
        <div style="flex: 1 1 calc(50% - 15px); min-width: 250px; background: #f8f9fa; border-radius: 12px; padding: 20px; border-left: 4px solid #0984e3;">
            <h3 style="margin: 0 0 10px 0; color: #2d3436;">{c['name']}</h3>
            <p style="margin: 5px 0; color: #636e72; font-size: 13px;"><b>티커:</b> {c['ticker']}</p>
            <p style="margin: 5px 0; color: #636e72; font-size: 13px;"><b>현재가:</b> {c['price']}</p>
            <p style="margin: 5px 0; color: #636e72; font-size: 13px;"><b>시총:</b> {c['market_cap']}</p>
            <p style="margin: 5px 0; color: #636e72; font-size: 13px;"><b>섹터:</b> {c['sector']}</p>
        </div>
        """
    cards += '</div>'
    return cards

# =========================================================
# [함수 8] 키워드 추출
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"'{news_title}' 뉴스의 영어 키워드 2개만 콤마로. 단어만."
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'}, timeout=10)
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "money, business"

# =========================================================
# [함수 9] 이미지 검색
# =========================================================
def get_relevant_images_webp(query):
    if not PEXELS_API_KEY: 
        return []
    try:
        resp = requests.get("https://api.pexels.com/v1/search", 
                          headers={"Authorization": PEXELS_API_KEY}, 
                          params={"query": query, "per_page": 2, "orientation": "landscape"}, 
                          timeout=10)
        if resp.status_code == 200:
            return [p['src']['original'] + "?auto=compress&fm=webp&w=800" 
                   for p in resp.json().get('photos', [])]
    except:
        pass
    return []

# =========================================================
# [함수 10] 본문 작성 (강화 버전)
# =========================================================
def generate_content(news, images, dashboard, article_content, research_data, company_data):
    print("🧠 심층 칼럼 작성 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # 원문이 없어도 제목으로 글 작성 가능하도록 수정
    if article_content:
        article_part = f"\n[기사 본문 발췌]\n{article_content[:1200]}\n"
    else:
        article_part = "\n[참고: 기사 본문은 확보하지 못했으므로, 뉴스 제목을 기반으로 일반적인 경제 분석을 작성해주세요.]\n"
    
    company_summary = ""
    if company_data:
        company_summary = "\n[관련 기업 정보]\n"
        for c in company_data:
            company_summary += f"- {c['name']}: 시총 {c['market_cap']}, 주가 {c['price']}, 섹터 {c['sector']}\n"
    
    prompt = f"""
    당신은 경제/금융 전문 칼럼니스트입니다.
    아래 뉴스를 심층 분석하는 칼럼을 작성하세요.
    
    [뉴스 제목]
    {news.title}
    {article_part}
    {company_summary}
    
    [작성 가이드]
    1. 뉴스 제목에서 핵심 경제 이슈를 파악
    2. 관련된 경제 원리나 시장 메커니즘 설명
    3. 미국/한국 관련 기업이 있다면 어떤 영향을 받는지 분석
    4. 투자자 관점에서 의미있는 인사이트 제공
    5. 리스크 요인도 함께 언급
    
    [HTML 구조]
    [[DASHBOARD]]
    
    <h2>🔥 [독자의 관심을 끄는 소제목]</h2>
    <p>[이 뉴스가 왜 중요한지 후킹 - 3문장]</p>
    
    [[IMAGE_1]]
    
    <h2>📚 경제 원리 해부</h2>
    <p>[이 뉴스와 관련된 경제 개념 설명 - 5문장 이상]</p>
    <ul>
      <li>핵심 포인트 1</li>
      <li>핵심 포인트 2</li>
      <li>핵심 포인트 3</li>
    </ul>
    
    <h2>🏢 관련 기업 분석</h2>
    <p>[이 뉴스가 기업들에게 미치는 영향 - 4문장 이상]</p>
    
    [[COMPANY_CARDS]]
    
    [[IMAGE_2]]
    
    <h2>💰 투자자가 알아야 할 것</h2>
    <p>[구체적인 투자 인사이트와 전망 - 4문장 이상]</p>
    
    <h2>⚠️ 리스크 체크</h2>
    <p>[주의해야 할 불확실성이나 리스크 - 3문장 이상]</p>
    
    <p><strong>결론:</strong> [핵심 메시지 1문장 정리]</p>
    <hr>
    <p style="color:grey; font-size:0.8em; text-align:center;">📰 출처: <a href="{news.link}">{news.title}</a></p>
    <p style="color:grey; font-size:0.8em; text-align:center;">⚠️ 본 글은 투자 권유가 아니며, 투자 판단의 책임은 투자자 본인에게 있습니다.</p>
    
    [필수 규칙]
    - HTML 태그만 출력 (```html 블록 절대 금지)
    - 해요체 사용
    - 전문 용어는 괄호로 쉽게 풀이
    - 각 섹션 최소 3문장 이상
    - [[DASHBOARD]], [[IMAGE_1]], [[IMAGE_2]], [[COMPANY_CARDS]]는 정확히 그대로 출력
    """
    
    for attempt in range(3):
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, 
                              headers={'Content-Type': 'application/json'}, 
                              timeout=30)
            if res.status_code == 200:
                raw = res.json()['candidates'][0]['content']['parts'][0]['text']
                clean = raw.replace("```html", "").replace("```", "").strip()
                
                # 치환
                clean = clean.replace("[[DASHBOARD]]", dashboard)
                clean = clean.replace("[[COMPANY_CARDS]]", make_company_cards(company_data))
                
                img1 = f'<img src="{images[0]}" style="width:100%; border-radius:12px; margin:25px 0;">' if len(images) > 0 else ""
                img2 = f'<img src="{images[1]}" style="width:100%; border-radius:12px; margin:25px 0;">' if len(images) > 1 else img1
                
                clean = clean.replace("[[IMAGE_1]]", img1)
                clean = clean.replace("[[IMAGE_2]]", img2)
                
                # 최소 길이 체크 완화 (300자 이상이면 OK)
                if len(clean) > 300:
                    print(f"✅ 글 작성 완료 ({len(clean)}자)")
                    return clean
                else:
                    print(f"⚠️ 글이 너무 짧음 ({len(clean)}자), 재시도...")
                    time.sleep(3)
                    
            elif res.status_code == 429:
                print("⏳ Rate limit, 30초 대기...")
                time.sleep(30)
        except Exception as e:
            print(f"❌ 시도 {attempt+1}/3 실패: {e}")
            time.sleep(5)
    
    return None

# =========================================================
# [함수 11] 제목 생성
# =========================================================
def generate_title(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"'{news_title}' 뉴스의 블로그 제목 1개만. 도파민 자극형. 특수문자 금지. 제목만 출력."
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, 
                          headers={'Content-Type': 'application/json'}, 
                          timeout=10)
        title = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        return title.split('\n')[0].replace('"', '').replace("*", "").strip()
    except:
        return news_title

# =========================================================
# [메인 실행]
# =========================================================
def run_bot():
    print("▶️ 경제 심층 분석 봇 시작")
    try:
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        news_list = get_business_news_list()
        if not news_list:
            print("❌ 뉴스 없음")
            return

        target = None
        for news in news_list:
            print(f"\n{'='*60}\n🔎 {news.title}")
            if check_is_duplicate(service, news.title):
                print("🚫 중복")
                continue
            target = news
            break
        
        if not target:
            print("😴 새 뉴스 없음")
            return

        print(f"\n✅ 선택: {target.title}\n{'='*60}\n")

        # ★★★ 핵심 파이프라인: 3단계 폴백 시스템 ★★★
        # 1단계: 원문 크롤링 시도
        article_content = fetch_article_content(target.link)
        
        # 2단계: 크롤링 실패 시 → 비슷한 기사들 찾아서 크롤링
        if not article_content:
            print("📡 Plan B: 비슷한 기사들에서 정보 수집 시도...")
            article_content = find_related_articles(target.title, news_list)
        
        # 3단계: 그것도 실패 시 → AI가 뉴스 분석
        if not article_content:
            print("🤖 Plan C: AI 지식 기반으로 분석...")
            article_content = ask_ai_about_news(target.title)
        
        # 5단계: 기업 리서치
        research_data = research_companies(target.title, article_content)
        
        company_data = []
        if research_data:
            all_companies = research_data.get('us_companies', []) + research_data.get('kr_companies', [])
            company_data = get_company_info(all_companies)
        
        keywords = get_search_keywords(target.title)
        images = get_relevant_images_webp(keywords)
        dashboard = get_dashboard_html()
        
        content = generate_content(target, images, dashboard, article_content, research_data, company_data)
        
        if not content:
            print("❌ 글 작성 실패")
            return

        title = generate_title(target.title)
        print(f"\n📤 제목: {title}")
        
        body = {"kind": "blogger#post", "title": title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"🎉 업로드 완료! ({len(content)}자)")

    except Exception as e:
        print(f"⛔ 오류: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    run_bot()
