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
# [설정]
# =========================================================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')
BLOG_ID = os.environ.get('MONEY_BLOG_ID')

if not GEMINI_API_KEY or not BLOG_ID:
    print("❌ 환경변수 누락")
    exit(1)

try:
    CLIENT_JSON = json.loads(os.environ.get('CLIENT_JSON', '{}'))
    TOKEN_JSON = json.loads(os.environ.get('TOKEN_JSON', '{}'))
except:
    print("⛔ 토큰 로딩 실패")
    exit(1)

MODEL_NAME = "gemini-2.0-flash-exp"

# =========================================================
# [대시보드]
# =========================================================
def get_dashboard_html():
    data = {"btc":{"price":0,"chg":0,"name":"비트코인"},"snp":{"price":0,"chg":0,"name":"S&P 500"},"nas":{"price":0,"chg":0,"name":"나스닥"},"kos":{"price":0,"chg":0,"name":"코스피"},"kdq":{"price":0,"chg":0,"name":"코스닥"}}
    tickers = {'^GSPC':'snp','^IXIC':'nas','^KS11':'kos','^KQ11':'kdq'}
    try:
        for ticker, key in tickers.items():
            hist = yf.Ticker(ticker).history(period="2d")
            if len(hist)>=2:
                data[key]['price']=hist['Close'].iloc[-1]
                data[key]['chg']=((hist['Close'].iloc[-1]-hist['Close'].iloc[-2])/hist['Close'].iloc[-2])*100
    except:pass
    try:
        res=requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=krw&include_24hr_change=true",timeout=5).json()
        data['btc']['price']=res['bitcoin']['krw']
        data['btc']['chg']=res['bitcoin']['krw_24h_change']
    except:pass
    
    items=""
    for key in ['btc','snp','nas','kos','kdq']:
        color,arrow=("#d63031","▲")if data[key]['chg']>=0 else("#0984e3","▼")
        pfmt=f"{data[key]['price']:,.0f}"if key=='btc'else f"{data[key]['price']:,.2f}"
        items+=f'<div style="flex:1 1 18%;min-width:100px;margin:5px;padding:10px;background:#fff;border-radius:8px;text-align:center;"><div style="font-size:11px;color:#888;">{data[key]["name"]}</div><div style="font-size:14px;font-weight:800;color:{color};">{arrow} {pfmt}</div><div style="font-size:10px;color:{color};">({data[key]["chg"]:.2f}%)</div></div>'
    return f'<div style="margin-bottom:30px;background:#f8f9fa;border-radius:12px;padding:15px;"><h3 style="text-align:center;margin:0 0 10px 0;font-size:16px;">⚡ 시장 현황</h3><div style="display:flex;flex-wrap:wrap;justify-content:center;gap:5px;">{items}</div></div>'

# =========================================================
# [뉴스, 중복, 크롤링]
# =========================================================
def get_business_news_list():
    try:
        feed=feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko")
        if feed.entries:return feed.entries[:8]  # ★ 8개로 증가
    except:pass
    return[]

def check_is_duplicate(service,news_title):
    try:
        for post in service.posts().list(blogId=BLOG_ID,maxResults=10).execute().get('items',[]):
            if news_title in post.get('content',''):return True
    except:pass
    return False

def fetch_article_content(url):
    try:
        text=trafilatura.extract(trafilatura.fetch_url(url))
        if text and len(text)>100:
            print(f"✅ {len(text)}자")
            return text[:3000]  # ★ 3000자로 증가
    except:pass
    return None

# =========================================================
# [★ 여러 기사 종합 분석 - 핵심!]
# =========================================================
def collect_multiple_sources(target_news, all_news_list):
    """같은 주제의 기사 3-5개를 모아서 교차 분석"""
    print("📰 여러 출처에서 정보 수집 중...")
    
    sources = []
    target_keywords = set(target_news.title.split())
    
    # 1. 타겟 기사 크롤링
    content1 = fetch_article_content(target_news.link)
    if content1:
        sources.append({
            'title': target_news.title,
            'content': content1,
            'link': target_news.link
        })
    
    # 2. 비슷한 기사 3-4개 더 찾기
    for news in all_news_list:
        if news.title == target_news.title:
            continue
        if len(set(news.title.split()) & target_keywords) >= 2:
            content = fetch_article_content(news.link)
            if content:
                sources.append({
                    'title': news.title,
                    'content': content,
                    'link': news.link
                })
                if len(sources) >= 4:  # 총 4개 출처
                    break
    
    print(f"✅ {len(sources)}개 출처 수집 완료")
    return sources

def synthesize_sources(sources):
    """여러 출처를 AI가 종합 분석"""
    print("🧠 여러 출처 종합 분석...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    sources_text = ""
    for idx, src in enumerate(sources, 1):
        sources_text += f"\n[출처 {idx}] {src['title']}\n{src['content'][:800]}\n"
    
    prompt = f"""
    여러 경제 뉴스 출처를 종합하여 심층 분석을 작성하세요.
    
    {sources_text}
    
    [분석 방법]
    1. 공통점: 모든 출처가 공통으로 언급하는 핵심 사실
    2. 차이점: 출처마다 다르게 해석하거나 강조하는 부분
    3. 숨겨진 맥락: 기사에서 명시하지 않았지만 중요한 배경
    4. 전문가 관점: 경제학자라면 어떻게 볼지
    5. 일반인 영향: 평범한 사람의 삶에 미치는 구체적 영향
    
    5-6문단, 1500자 이상으로 작성.
    """
    
    try:
        res = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}]}, timeout=30)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text) > 200:
                print(f"✅ {len(text)}자 종합 분석 완료")
                return text[:3000]
    except:pass
    return None

# =========================================================
# [심층 리서치]
# =========================================================
def research_economy_deeply(news_title, synthesized_analysis):
    print("🔬 경제 원리 심층 리서치...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    context = synthesized_analysis[:1500] if synthesized_analysis else news_title
    
    prompt = f"""
    {context}
    
    다음을 각 4-5문장으로:
    1. economic_principle: 이 뉴스와 관련된 경제 이론 (케인즈, 통화주의 등)
    2. historical_context: 과거 비슷한 사례 (최소 2개 이상)
    3. market_mechanism: 시장 영향 경로를 A→B→C 단계별로
    4. expert_opinions: 경제학자들의 찬반 양론
    5. future_scenario: 3년 후 시나리오 3가지
    6. personal_impact: 월급쟁이/자영업자/투자자에게 미치는 구체적 영향
    
    JSON:
    {{"economic_principle":"...","historical_context":"...","market_mechanism":"...","expert_opinions":"...","future_scenario":"...","personal_impact":"..."}}
    """
    
    try:
        res = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}]}, timeout=25)
        if res.status_code == 200:
            match = re.search(r'\{.*\}', res.json()['candidates'][0]['content']['parts'][0]['text'], re.DOTALL)
            if match:
                print("✅ 리서치 완료")
                return json.loads(match.group())
    except:pass
    return None

# =========================================================
# [기업 리서치]
# =========================================================
def research_companies(synthesized_analysis):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    try:
        res = requests.post(url, json={"contents":[{"parts":[{"text":f"{synthesized_analysis[:1000]}\n\n미국/한국 기업 각 1-2개 JSON:{{'us_companies':['Apple(AAPL)'],'kr_companies':['삼성전자(005930.KS)']}}"}]}]}, timeout=15)
        if res.status_code == 200:
            match = re.search(r'\{.*\}', res.json()['candidates'][0]['content']['parts'][0]['text'], re.DOTALL)
            if match:return json.loads(match.group())
    except:pass
    return None

def get_company_info(companies_list):
    results = []
    for company_str in companies_list:
        try:
            ticker = re.search(r'\(([^)]+)\)', company_str).group(1)
            name = company_str.split('(')[0].strip()
            info = yf.Ticker(ticker).info
            market_cap = info.get('marketCap', 0)
            cap_display = f"{market_cap/1e12:.1f}조원" if 'KS' in ticker and market_cap else (f"${market_cap/1e9:.1f}B" if market_cap else "N/A")
            price = info.get('currentPrice', 0) or (yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1] if len(yf.Ticker(ticker).history(period="1d")) > 0 else 0)
            results.append({'name':name,'ticker':ticker,'price':f"${price:.2f}" if price else "N/A",'market_cap':cap_display,'sector':info.get('sector','N/A')})
        except:continue
    return results

def make_company_cards(company_data):
    if not company_data:return ""
    cards = '<div style="display:flex;flex-wrap:wrap;gap:15px;margin:25px 0;">'
    for c in company_data:
        cards += f'<div style="flex:1 1 calc(50%-15px);min-width:250px;background:#f8f9fa;border-radius:12px;padding:20px;border-left:4px solid #0984e3;"><h3 style="margin:0 0 10px 0;">{c["name"]}</h3><p style="margin:5px 0;font-size:13px;"><b>티커:</b> {c["ticker"]}</p><p style="margin:5px 0;font-size:13px;"><b>현재가:</b> {c["price"]}</p><p style="margin:5px 0;font-size:13px;"><b>시총:</b> {c["market_cap"]}</p><p style="margin:5px 0;font-size:13px;"><b>섹터:</b> {c["sector"]}</p></div>'
    cards += '</div>'
    return cards

# =========================================================
# [키워드, 이미지]
# =========================================================
def get_search_keywords(news_title):
    try:
        res=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}",json={"contents":[{"parts":[{"text":f"'{news_title}' 영어 키워드 2개"}]}]},timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:return "economy, finance"

def get_relevant_images_webp(query):
    if not PEXELS_API_KEY:return []
    try:
        resp=requests.get("https://api.pexels.com/v1/search",headers={"Authorization":PEXELS_API_KEY},params={"query":query,"per_page":2},timeout=10)
        if resp.status_code==200:return [p['src']['original']+"?w=800" for p in resp.json().get('photos',[])]
    except:pass
    return []

def clean_markdown(text):
    text=re.sub(r'\*\*([^\*]+)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'\*([^\*]+)\*',r'<em>\1</em>',text)
    text=text.replace('###','').replace('##','').replace('```','').replace('**','')
    text=re.sub(r'<i>(\d+)</i>',r'\1',text)
    return re.sub(r'</i>|<i>','',text)

# =========================================================
# [★ 초장문 독창적 칼럼 작성 - 애드센스 승인용!]
# =========================================================
def generate_adsense_approved_content(news, images, dashboard, sources, synthesized_analysis, research_data, company_data):
    """2500자 이상, 완전 독창적 분석"""
    print("🧠 애드센스 승인용 초장문 칼럼 작성...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # 출처 정보
    sources_ref = ""
    if sources:
        sources_ref = "\n[참고한 뉴스 출처]\n"
        for idx, src in enumerate(sources, 1):
            sources_ref += f"{idx}. {src['title']}\n"
    
    # 종합 분석
    analysis_part = f"\n[여러 출처 종합 분석]\n{synthesized_analysis[:1500]}\n" if synthesized_analysis else ""
    
    # 리서치 데이터
    research_section = ""
    if research_data:
        research_section = f"""
[경제 전문 지식]
- 경제 이론: {research_data.get('economic_principle', 'N/A')}
- 역사적 사례: {research_data.get('historical_context', 'N/A')}
- 시장 메커니즘: {research_data.get('market_mechanism', 'N/A')}
- 전문가 의견: {research_data.get('expert_opinions', 'N/A')}
- 미래 시나리오: {research_data.get('future_scenario', 'N/A')}
- 개인 영향: {research_data.get('personal_impact', 'N/A')}
"""
    
    company_summary = ""
    if company_data:
        company_summary = "\n[관련 기업]\n" + "\n".join([f"- {c['name']}: {c['market_cap']}, {c['sector']}" for c in company_data])
    
    prompt = f"""
    당신은 15년 경력 경제 칼럼니스트입니다.
    아래 정보를 바탕으로 **완전히 독창적인 심층 분석 칼럼**을 작성하세요.
    
    [주제] {news.title}
    {sources_ref}
    {analysis_part}
    {research_section}
    {company_summary}
    
    [애드센스 승인 필수 조건]
    1. **독창성**: 단순 뉴스 요약 절대 금지! 개인 전문가 관점으로 재해석
    2. **충분한 길이**: 최소 2500자 이상
    3. **부가 가치**: 뉴스에서 다루지 않은 심층 분석 포함
    4. **여러 관점**: 찬성/반대 양측 의견 모두 제시
    5. **실용성**: 독자의 삶에 직접 도움되는 정보
    6. **출처 명시**: 투명하게 참고 출처 밝히기
    
    [작성 가이드]
    - 1인칭 전문가 시점 ("제가 보기에", "경제학적으로 분석하면")
    - 구체적 숫자와 사례
    - 독자 질문 예상하고 답변
    - 논쟁적 이슈는 양측 입장 균형있게
    
    HTML 구조:
    DASHBOARDHERE
    
    <div style="background:#fff3cd;padding:15px;border-left:4px solid #ffc107;margin:20px 0;">
    <strong>📌 편집자 주</strong><p style="margin:5px 0 0 0;font-size:14px;">이 글은 {len(sources)}개의 뉴스 출처를 교차 분석하고, 경제 이론과 역사적 맥락을 더해 작성한 독창적 칼럼입니다.</p>
    </div>
    
    <h2>🔥 [독자 호기심 자극하는 제목]</h2>
    <p>[이 뉴스가 왜 중요한지 - 5문장으로 후킹]</p>
    
    IMAGE1HERE
    
    <h2>📊 뉴스 팩트 체크</h2>
    <p>[여러 출처에서 공통으로 언급한 핵심 사실 - 6문장]</p>
    <ul><li>팩트 1</li><li>팩트 2</li><li>팩트 3</li></ul>
    
    <h2>🎓 경제학자의 눈으로 보기</h2>
    <p>[경제 이론으로 분석 - 8문장 이상]</p>
    <p><em>"케인즈라면 이렇게 말했을 것입니다..."</em></p>
    
    <h2>📖 과거에도 있었던 일</h2>
    <p>[역사적 사례 2개 이상 비교 - 7문장]</p>
    
    IMAGE2HERE
    
    <h2>💸 돈의 흐름을 따라가면</h2>
    <p>[시장 영향 경로를 단계별로 - 7문장]</p>
    <p>1단계: [...]<br>2단계: [...]<br>3단계: [...]</p>
    
    <h2>🏢 주목할 기업들</h2>
    <p>[기업이 받을 영향 분석 - 5문장]</p>
    COMPANYCARDSHERE
    
    <h2>⚖️ 찬성 vs 반대</h2>
    <p><strong>찬성 입장:</strong> [3문장]</p>
    <p><strong>반대 입장:</strong> [3문장]</p>
    <p><strong>제 생각:</strong> [2문장]</p>
    
    <h2>💰 당신의 지갑에 미치는 영향</h2>
    <p>[월급쟁이/자영업자/투자자별 구체적 영향 - 6문장]</p>
    
    <h2>🔮 3년 후 시나리오</h2>
    <p><strong>낙관:</strong> [2문장]</p>
    <p><strong>비관:</strong> [2문장]</p>
    <p><strong>현실:</strong> [2문장]</p>
    
    <h2>⚠️ 놓치면 안 되는 리스크</h2>
    <p>[전문가들이 우려하는 점 - 5문장]</p>
    
    <p><strong>결론:</strong> [핵심 메시지 3문장]</p>
    
    <hr>
    <div style="background:#f8f9fa;padding:15px;border-radius:8px;margin:20px 0;">
    <p style="font-size:13px;color:#666;margin:5px 0;"><strong>📰 참고 출처</strong></p>
    {sources_ref.replace('[참고한 뉴스 출처]','').strip()}
    <p style="font-size:12px;color:#999;margin:10px 0 0 0;">본 칼럼은 위 뉴스들을 독립적으로 분석한 저자의 견해이며, 투자 권유가 아닙니다.</p>
    </div>
    
    규칙: HTML만, 해요체, 각 섹션 5문장 이상
    """
    
    for attempt in range(3):
        try:
            res = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}]}, 
                              headers={'Content-Type':'application/json'}, timeout=50)
            if res.status_code == 200:
                clean = clean_markdown(res.json()['candidates'][0]['content']['parts'][0]['text']).replace("```html","").replace("```","").strip()
                
                # 치환
                clean = clean.replace("DASHBOARDHERE", dashboard).replace("[[DASHBOARD]]", dashboard)
                clean = clean.replace("COMPANYCARDSHERE", make_company_cards(company_data)).replace("[[COMPANY_CARDS]]", make_company_cards(company_data))
                
                img1 = f'<img src="{images[0]}" style="width:100%;border-radius:12px;margin:25px 0;">' if len(images) > 0 else ""
                img2 = f'<img src="{images[1]}" style="width:100%;border-radius:12px;margin:25px 0;">' if len(images) > 1 else img1
                clean = clean.replace("IMAGE1HERE", img1).replace("IMAGE2HERE", img2).replace("[[IMAGE_1]]", img1).replace("[[IMAGE_2]]", img2)
                
                # ★ 최소 2000자 이상 (애드센스 승인용)
                if len(clean) > 2000:
                    print(f"✅ {len(clean)}자 완성 (애드센스 승인 기준 충족)")
                    return clean
                else:
                    print(f"⚠️ {len(clean)}자 - 너무 짧음, 재시도...")
                    
            time.sleep(3)
        except Exception as e:
            print(f"❌ {attempt+1}/3: {e}")
            time.sleep(5)
    return None

def generate_title(news_title):
    try:
        res=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}",
                        json={"contents":[{"parts":[{"text":f"'{news_title}' 블로그 제목 1개. 전문가 칼럼 느낌. 특수문자 금지."}]}]},timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')[0].replace('"','').replace('*','')
    except:return news_title

# =========================================================
# [메인]
# =========================================================
def run_bot():
    print("▶️ 애드센스 승인용 경제 블로그 봇")
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

        # ★★★ 애드센스 승인용 강화 파이프라인 ★★★
        # 1단계: 여러 출처 수집 (3-5개)
        sources = collect_multiple_sources(target, news_list)
        
        # 2단계: 여러 출처 종합 분석
        synthesized = synthesize_sources(sources) if sources else None
        
        # 3단계: 경제 원리 심층 리서치
        research_data = research_economy_deeply(target.title, synthesized)
        
        # 4단계: 기업 정보
        company_research = research_companies(synthesized) if synthesized else None
        company_data = []
        if company_research:
            all_companies = company_research.get('us_companies', []) + company_research.get('kr_companies', [])
            company_data = get_company_info(all_companies)
        
        # 5-6단계: 이미지, 대시보드
        keywords = get_search_keywords(target.title)
        images = get_relevant_images_webp(keywords)
        dashboard = get_dashboard_html()
        
        # 7단계: ★ 애드센스 승인용 초장문 칼럼 작성
        content = generate_adsense_approved_content(target, images, dashboard, sources, synthesized, research_data, company_data)
        if not content:
            print("❌ 작성 실패")
            return

        title = generate_title(target.title)
        print(f"\n📤 제목: {title}")
        print(f"📏 글자수: {len(content)}자")
        
        body = {"kind":"blogger#post","title":title,"content":content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"🎉 완료!")

    except Exception as e:
        print(f"⛔ 오류: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    run_bot()
