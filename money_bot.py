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
                data[key]['price'] = hist['Close'].iloc[-1]
                data[key]['chg'] = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-2]) / hist['Close'].iloc[-2]) * 100
    except Exception as e:
        print(f"⚠️ 주식 데이터 실패: {e}")

    try:
        res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=krw&include_24hr_change=true", timeout=5).json()
        data['btc']['price'] = res['bitcoin']['krw']
        data['btc']['chg'] = res['bitcoin']['krw_24h_change']
    except:
        pass

    def get_style(chg):
        return ("#d63031", "▲") if chg >= 0 else ("#0984e3", "▼")

    items_html = ""
    for key in ['btc', 'snp', 'nas', 'kos', 'kdq']:
        color, arrow = get_style(data[key]['chg'])
        price_fmt = f"{data[key]['price']:,.0f}" if key == 'btc' else f"{data[key]['price']:,.2f}"
        items_html += f'<div style="flex: 1 1 18%; min-width: 100px; margin: 5px; padding: 10px; background: #fff; border-radius: 8px; text-align: center;"><div style="font-size: 11px; color: #888;">{data[key]["name"]}</div><div style="font-size: 14px; font-weight: 800; color: {color};">{arrow} {price_fmt}</div><div style="font-size: 10px; color: {color};">({data[key]["chg"]:.2f}%)</div></div>'
    
    return f'<div style="font-family: -apple-system; margin-bottom: 30px; background: #f8f9fa; border-radius: 12px; padding: 15px;"><h3 style="text-align: center; margin: 0 0 10px 0; font-size: 16px;">⚡ Market Flow Check</h3><div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 5px;">{items_html}</div></div>'

# =========================================================
# [함수 2-6] 뉴스, 중복, 크롤링, 관련기사, AI분석
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
        if news.title != target_title and len(set(news.title.split()) & target_keywords) >= 2:
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
    prompt = f"'{news_title}' 경제 뉴스를 5-6문단으로 심층 분석: 배경, 경제 원리, 역사적 맥락, 영향, 전망, 리스크"
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=20)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text) > 150:
                print(f"✅ {len(text)}자 생성")
                return text[:2500]
    except:
        pass
    return None

# =========================================================
# [함수 7] ★ 경제 원리 심층 리서치 (핵심 추가!)
# =========================================================
def research_economy_deeply(news_title, article_content):
    """테크/과학 코드처럼 심층 리서치"""
    print("🔬 경제 원리 심층 리서치 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    context = f"기사 내용: {article_content[:1500]}" if article_content else f"제목: {news_title}"
    
    prompt = f"""
    다음 경제/금융 뉴스를 분석하여 독자들이 알아야 할 경제 지식을 정리해주세요.
    
    {context}
    
    다음 항목들을 각각 3-4문장으로 상세히 설명:
    1. 핵심 경제 원리: 이 뉴스와 관련된 경제학 개념 (예: 금리, 인플레이션, 공급망, 환율, 양적완화, 재정정책 등)을 교과서 수준으로 설명
    2. 역사적 맥락: 과거 비슷한 경제 사건이나 위기 사례 (예: 2008 금융위기, 1997 IMF, 닷컴버블 등)
    3. 시장 메커니즘: 이 뉴스가 주식/채권/부동산 시장에 미치는 구체적 영향 경로
    4. 전문가 의견: 경제학자, 애널리스트들의 평가와 논쟁 (찬반 의견)
    5. 미래 시나리오: 3-5년 후 이 이슈가 경제에 미칠 영향 예측
    
    JSON으로 출력:
    {{
      "economic_principle": "...",
      "historical_context": "...",
      "market_mechanism": "...",
      "expert_opinions": "...",
      "future_scenario": "..."
    }}
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, 
                          headers={'Content-Type': 'application/json'}, timeout=20)
        if res.status_code == 200:
            raw = res.json()['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                print("✅ 경제 원리 리서치 완료")
                return data
    except Exception as e:
        print(f"⚠️ 리서치 실패: {e}")
    return None

# =========================================================
# [함수 8] 기업 리서치
# =========================================================
def research_companies(news_title, article_content):
    print("🏢 기업 리서치...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    context = article_content[:1000] if article_content else news_title
    
    prompt = f"{context}\n\n미국 기업 1-2개(티커), 한국 기업 1-2개(티커) JSON:\n{{'us_companies':['Apple(AAPL)'],'kr_companies':['삼성전자(005930.KS)']}}"
    
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
            cap_display = f"{market_cap/1e12:.1f}조원" if 'KS' in ticker and market_cap else (f"${market_cap/1e9:.1f}B" if market_cap else "N/A")
            
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
        cards += f'<div style="flex: 1 1 calc(50% - 15px); min-width: 250px; background: #f8f9fa; border-radius: 12px; padding: 20px; border-left: 4px solid #0984e3;"><h3 style="margin: 0 0 10px 0;">{c["name"]}</h3><p style="margin: 5px 0; font-size: 13px;"><b>티커:</b> {c["ticker"]}</p><p style="margin: 5px 0; font-size: 13px;"><b>현재가:</b> {c["price"]}</p><p style="margin: 5px 0; font-size: 13px;"><b>시총:</b> {c["market_cap"]}</p><p style="margin: 5px 0; font-size: 13px;"><b>섹터:</b> {c["sector"]}</p></div>'
    cards += '</div>'
    return cards

# =========================================================
# [함수 9-10] 키워드, 이미지
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": f"'{news_title}' 영어 키워드 2개만"}]}]}, timeout=10)
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
# [함수 11] 마크다운 클리너
# =========================================================
def clean_markdown(text):
    text = re.sub(r'\*\*([^\*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^\*]+)\*', r'<em>\1</em>', text)
    text = text.replace('###', '').replace('##', '').replace('#', '').replace('```', '').replace('**', '').replace('__', '')
    text = re.sub(r'<i>(\d+)</i>', r'\1', text)
    text = re.sub(r'</i>|<i>', '', text)
    return text

# =========================================================
# [함수 12] ★ 심층 경제 칼럼 작성 (리서치 데이터 활용!)
# =========================================================
def generate_deep_content(news, images, dashboard, article_content, research_data, company_data):
    print("🧠 심층 경제 칼럼 작성...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    article_part = f"[기사 발췌]\n{article_content[:1200]}" if article_content else ""
    
    # ★ 리서치 데이터 통합
    research_section = ""
    if research_data:
        research_section = f"""
[참고할 경제 지식]
- 경제 원리: {research_data.get('economic_principle', 'N/A')}
- 역사적 맥락: {research_data.get('historical_context', 'N/A')}
- 시장 메커니즘: {research_data.get('market_mechanism', 'N/A')}
- 전문가 의견: {research_data.get('expert_opinions', 'N/A')}
- 미래 시나리오: {research_data.get('future_scenario', 'N/A')}
"""
    
    company_summary = ""
    if company_data:
        company_summary = "\n[관련 기업]\n" + "\n".join([f"- {c['name']}: {c['market_cap']}, {c['sector']}" for c in company_data])
    
    prompt = f"""
    당신은 10년 경력의 경제 전문 칼럼니스트입니다.
    아래 뉴스를 단순 요약이 아닌, **교과서 수준의 심층 경제 해설**로 작성하세요.
    
    [뉴스] {news.title}
    {article_part}
    {research_section}
    {company_summary}
    
    [작성 가이드 - 깊이 있는 분석]
    1. **경제 원리**: 기초 개념부터 상세히 설명 (중학생도 이해 가능하게)
    2. **역사 비교**: 과거 사례와 비교 분석
    3. **메커니즘**: 돈의 흐름과 영향 경로를 단계별로
    4. **다각적 관점**: 찬반 의견 모두 제시
    5. **충분한 길이**: 최소 1500자 이상
    
    HTML 구조:
    DASHBOARDHERE
    <h2>🔥 [도발적 소제목]</h2>
    <p>[후킹 4문장]</p>
    IMAGE1HERE
    <h2>📚 경제 원리의 기초</h2>
    <p>[개념을 교과서 수준으로 7문장]</p>
    <ul><li>원리 1</li><li>원리 2</li><li>원리 3</li></ul>
    <h2>🔗 과거에도 있었다: 역사적 맥락</h2>
    <p>[비슷한 과거 사례 5문장]</p>
    <h2>💸 돈의 흐름: 시장 메커니즘</h2>
    <p>[영향 경로를 단계별로 6문장]</p>
    IMAGE2HERE
    <h2>🏢 관련 기업 분석</h2>
    <p>[기업 영향 4문장]</p>
    COMPANYCARDSHERE
    <h2>🔮 3년 후 시나리오</h2>
    <p>[미래 예측 5문장]</p>
    <h2>⚠️ 전문가들의 우려</h2>
    <p>[리스크와 반대 의견 4문장]</p>
    <p><strong>결론:</strong> [2문장]</p>
    <hr><p style="color:grey; font-size:0.85em;">📰 출처: {news.title}<br>⚠️ 투자 판단은 본인 책임</p>
    
    규칙: HTML만, 해요체, 각 섹션 4문장 이상
    """
    
    for attempt in range(3):
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=40)
            if res.status_code == 200:
                raw = res.json()['candidates'][0]['content']['parts'][0]['text']
                clean = clean_markdown(raw).replace("```html", "").replace("```", "").strip()
                
                # 치환
                clean = clean.replace("DASHBOARDHERE", dashboard).replace("[[DASHBOARD]]", dashboard)
                clean = clean.replace("COMPANYCARDSHERE", make_company_cards(company_data)).replace("[[COMPANY_CARDS]]", make_company_cards(company_data))
                
                img1 = f'<img src="{images[0]}" style="width:100%; border-radius:12px; margin:25px 0;">' if len(images) > 0 else ""
                img2 = f'<img src="{images[1]}" style="width:100%; border-radius:12px; margin:25px 0;">' if len(images) > 1 else img1
                clean = clean.replace("IMAGE1HERE", img1).replace("IMAGE2HERE", img2).replace("[[IMAGE_1]]", img1).replace("[[IMAGE_2]]", img2)
                
                # ★ 최소 길이 체크 (1200자 이상)
                if len(clean) > 1200:
                    print(f"✅ {len(clean)}자 완성")
                    return clean
                else:
                    print(f"⚠️ 너무 짧음 ({len(clean)}자), 재시도...")
                    
            time.sleep(3)
        except Exception as e:
            print(f"❌ 시도 {attempt+1}: {e}")
            time.sleep(5)
    return None

def generate_title(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": f"'{news_title}' 블로그 제목 1개. 도파민 자극. 특수문자 금지."}]}]}, timeout=10)
        title = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        return title.split('\n')[0].replace('"', '').replace('*', '').strip()
    except:
        return news_title

# =========================================================
# [메인 실행]
# =========================================================
def run_bot():
    print("▶️ 경제 심층 분석 봇 시작 (애드센스 승인용)")
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

        # ★★★ 강화된 파이프라인 ★★★
        # 1-3단계: 원문 수집 (3단계 폴백)
        article_content = fetch_article_content(target.link)
        if not article_content:
            article_content = find_related_articles(target.title, news_list)
        if not article_content:
            article_content = ask_ai_about_economy(target.title)
        
        # 4단계: ★ 경제 원리 심층 리서치 (핵심 추가!)
        research_data = research_economy_deeply(target.title, article_content)
        
        # 5단계: 기업 정보
        company_research = research_companies(target.title, article_content)
        company_data = []
        if company_research:
            all_companies = company_research.get('us_companies', []) + company_research.get('kr_companies', [])
            company_data = get_company_info(all_companies)
        
        # 6-7단계: 이미지, 대시보드
        keywords = get_search_keywords(target.title)
        images = get_relevant_images_webp(keywords)
        dashboard = get_dashboard_html()
        
        # 8단계: ★ 리서치 데이터 활용해서 심층 칼럼 작성
        content = generate_deep_content(target, images, dashboard, article_content, research_data, company_data)
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
