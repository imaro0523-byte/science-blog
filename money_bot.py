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

GEMINI_API_KEY=os.environ.get('GEMINI_API_KEY')
PEXELS_API_KEY=os.environ.get('PEXELS_API_KEY')
BLOG_ID = os.environ.get('BLOG_ID')
if not GEMINI_API_KEY or not BLOG_ID:exit(1)
try:
    CLIENT_JSON=json.loads(os.environ.get('CLIENT_JSON','{}'))
    TOKEN_JSON=json.loads(os.environ.get('TOKEN_JSON','{}'))
except:exit(1)
MODEL_NAME = "gemini-3-flash-preview"

def get_dashboard_html():
    data={"btc":{"price":0,"chg":0,"name":"비트코인"},"snp":{"price":0,"chg":0,"name":"S&P 500"},"nas":{"price":0,"chg":0,"name":"나스닥"},"kos":{"price":0,"chg":0,"name":"코스피"},"kdq":{"price":0,"chg":0,"name":"코스닥"}}
    tickers={'^GSPC':'snp','^IXIC':'nas','^KS11':'kos','^KQ11':'kdq'}
    try:
        for ticker,key in tickers.items():
            hist=yf.Ticker(ticker).history(period="2d")
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

def get_business_news_list():
    try:
        feed=feedparser.parse("https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko")
        if feed.entries:return feed.entries[:8]
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
        if text and len(text)>100:return text[:3000]
    except:pass
    return None

def collect_multiple_sources(target_news,all_news_list):
    sources=[]
    target_keywords=set(target_news.title.split())
    content1=fetch_article_content(target_news.link)
    if content1:sources.append({'title':target_news.title,'content':content1,'link':target_news.link})
    for news in all_news_list:
        if news.title!=target_news.title and len(set(news.title.split())&target_keywords)>=2:
            content=fetch_article_content(news.link)
            if content:
                sources.append({'title':news.title,'content':content,'link':news.link})
                if len(sources)>=4:break
    return sources

def synthesize_sources(sources):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    sources_text="\n".join([f"[출처{i+1}]{s['title']}\n{s['content'][:800]}"for i,s in enumerate(sources)])
    prompt=f"{sources_text}\n\n여러 경제 뉴스 종합. 공통점,차이점,숨겨진 맥락,전문가 관점,일반인 영향. 1500자+"
    try:
        res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=30)
        if res.status_code==200:
            text=res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text)>200:return text[:3000]
    except:pass
    return None

def research_economy_deeply(news_title,synthesized):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    context=synthesized[:1500]if synthesized else news_title
    prompt=f"{context}\n\n다음 각 4-5문장:\n1.economic_principle:경제 이론\n2.historical_context:과거 사례\n3.market_mechanism:시장 영향 경로\n4.expert_opinions:찬반 의견\n5.future_scenario:미래 시나리오\n6.personal_impact:개인 영향\nJSON"
    try:
        res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=25)
        if res.status_code==200:
            match=re.search(r'\{.*\}',res.json()['candidates'][0]['content']['parts'][0]['text'],re.DOTALL)
            if match:return json.loads(match.group())
    except:pass
    return None

def research_companies(synthesized):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    try:
        res=requests.post(url,json={"contents":[{"parts":[{"text":f"{synthesized[:1000]}\n\n미국/한국 기업 각 1-2개 JSON:{{'us_companies':['Apple(AAPL)'],'kr_companies':['삼성전자(005930.KS)']}}"}]}]},timeout=15)
        if res.status_code==200:
            match=re.search(r'\{.*\}',res.json()['candidates'][0]['content']['parts'][0]['text'],re.DOTALL)
            if match:return json.loads(match.group())
    except:pass
    return None

def get_company_info(companies_list):
    results=[]
    for company_str in companies_list:
        try:
            ticker=re.search(r'\(([^)]+)\)',company_str).group(1)
            name=company_str.split('(')[0].strip()
            info=yf.Ticker(ticker).info
            market_cap=info.get('marketCap',0)
            cap_display=f"{market_cap/1e12:.1f}조원"if'KS'in ticker and market_cap else(f"${market_cap/1e9:.1f}B"if market_cap else"N/A")
            price=info.get('currentPrice',0)or(yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1]if len(yf.Ticker(ticker).history(period="1d"))>0 else 0)
            results.append({'name':name,'ticker':ticker,'price':f"${price:.2f}"if price else"N/A",'market_cap':cap_display,'sector':info.get('sector','N/A')})
        except:continue
    return results

def make_company_cards(company_data):
    if not company_data:return""
    cards='<div style="display:flex;flex-wrap:wrap;gap:15px;margin:25px 0;">'
    for c in company_data:
        cards+=f'<div style="flex:1 1 calc(50%-15px);min-width:250px;background:#f8f9fa;border-radius:12px;padding:20px;border-left:4px solid #0984e3;"><h3 style="margin:0 0 10px 0;">{c["name"]}</h3><p style="margin:5px 0;font-size:13px;"><b>티커:</b>{c["ticker"]}</p><p style="margin:5px 0;font-size:13px;"><b>현재가:</b>{c["price"]}</p><p style="margin:5px 0;font-size:13px;"><b>시총:</b>{c["market_cap"]}</p><p style="margin:5px 0;font-size:13px;"><b>섹터:</b>{c["sector"]}</p></div>'
    cards+='</div>'
    return cards

def get_search_keywords(news_title):
    try:
        res=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}",json={"contents":[{"parts":[{"text":f"'{news_title}' 영어 키워드 2개"}]}]},timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:return"economy,finance"

def get_relevant_images_webp(query):
    if not PEXELS_API_KEY:return[]
    try:
        resp=requests.get("https://api.pexels.com/v1/search",headers={"Authorization":PEXELS_API_KEY},params={"query":query,"per_page":2},timeout=10)
        if resp.status_code==200:return[p['src']['original']+"?w=800"for p in resp.json().get('photos',[])]
    except:pass
    return[]

def clean_markdown(text):
    # ★ HDMR 같은 이상한 문자 제거
    text=re.sub(r'^[A-Z]{3,5}\s*\n','',text)  # 첫줄 대문자 3-5개 제거
    text=re.sub(r'\*\*([^\*]+)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'\*([^\*]+)\*',r'<em>\1</em>',text)
    text=text.replace('###','').replace('##','').replace('```','').replace('**','')
    text=re.sub(r'<i>(\d+)</i>',r'\1',text)
    text=re.sub(r'</i>|<i>','',text)
    return text.strip()

def generate_adsense_approved_content(news,images,dashboard,sources,synthesized,research_data,company_data):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # ★ 편집자 주 조건부 생성
    editor_note=""
    if sources and len(sources)>=2:
        editor_note=f'<div style="background:#fff3cd;padding:15px;border-left:4px solid #ffc107;margin:20px 0;"><strong>📌 편집자 주</strong><p style="margin:5px 0 0 0;font-size:14px;">이 글은 {len(sources)}개의 뉴스 출처를 교차 분석하고, 경제 이론과 역사적 맥락을 더해 작성한 독창적 칼럼입니다.</p></div>'
    
    sources_ref=""
    if sources:sources_ref="\n[참고]\n"+"\n".join([f"{i+1}.{s['title']}"for i,s in enumerate(sources)])
    analysis_part=f"\n[종합]\n{synthesized[:1500]}\n"if synthesized else""
    research_section=""
    if research_data:
        research_section=f"\n[지식]\n-원리:{research_data.get('economic_principle','N/A')}\n-역사:{research_data.get('historical_context','N/A')}\n-메커니즘:{research_data.get('market_mechanism','N/A')}\n-의견:{research_data.get('expert_opinions','N/A')}\n-미래:{research_data.get('future_scenario','N/A')}\n-영향:{research_data.get('personal_impact','N/A')}"
    coin_summary=""
    if company_data:coin_summary="\n[기업]\n"+"\n".join([f"-{c['name']}:{c['market_cap']},{c['sector']}"for c in company_data])
    
    prompt=f"""
    경제 칼럼니스트로 독창적 칼럼.
    
    [주제]{news.title}
    {sources_ref}
    {analysis_part}
    {research_section}
    {coin_summary}
    
    [애드센스]
    1.독창성 2.2500자+ 3.부가가치 4.다각도 5.실용성 6.출처
    
    HTML:
    DASHBOARDHERE
    EDITORHERE
    <h2>🔥 소제목</h2>
    <p>후킹 5문장</p>
    IMAGE1HERE
    <h2>📊 팩트</h2>
    <p>사실 6문장</p>
    <ul><li>팩트1</li><li>팩트2</li><li>팩트3</li></ul>
    <h2>🎓 경제 이론</h2>
    <p>분석 8문장</p>
    <h2>📖 과거 사례</h2>
    <p>역사 7문장</p>
    IMAGE2HERE
    <h2>💸 시장 메커니즘</h2>
    <p>영향 7문장</p>
    <h2>🏢 기업</h2>
    <p>분석 5문장</p>
    COMPANYCARDSHERE
    <h2>⚖️ 찬성vs반대</h2>
    <p><strong>찬성:</strong>3문장</p>
    <p><strong>반대:</strong>3문장</p>
    <p><strong>제 생각:</strong>2문장</p>
    <h2>💰 개인 영향</h2>
    <p>영향 6문장</p>
    <h2>🔮 시나리오</h2>
    <p><strong>낙관:</strong>2문장</p>
    <p><strong>비관:</strong>2문장</p>
    <p><strong>현실:</strong>2문장</p>
    <h2>⚠️ 리스크</h2>
    <p>위험 5문장</p>
    <p><strong>결론:</strong>3문장</p>
    <hr>
    <div style="background:#f8f9fa;padding:15px;">
    <p><strong>📰 출처</strong></p>
    {sources_ref.replace('[참고]','').strip()}
    <p style="font-size:12px;color:#999;">독립 분석, 투자 권유 아님</p>
    </div>
    
    규칙:HTML,해요체,5문장+
    """
    
    for attempt in range(3):
        try:
            res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=50)
            if res.status_code==200:
                clean=clean_markdown(res.json()['candidates'][0]['content']['parts'][0]['text']).replace("```html","").replace("```","").strip()
                clean=clean.replace("DASHBOARDHERE",dashboard).replace("[[DASHBOARD]]",dashboard)
                clean=clean.replace("EDITORHERE",editor_note).replace("[[EDITOR]]",editor_note)  # ★ 편집자 주
                clean=clean.replace("COMPANYCARDSHERE",make_company_cards(company_data)).replace("[[COMPANY_CARDS]]",make_company_cards(company_data))
                img1=f'<img src="{images[0]}" style="width:100%;border-radius:12px;margin:25px 0;">'if len(images)>0 else""
                img2=f'<img src="{images[1]}" style="width:100%;border-radius:12px;margin:25px 0;">'if len(images)>1 else img1
                clean=clean.replace("IMAGE1HERE",img1).replace("IMAGE2HERE",img2).replace("[[IMAGE_1]]",img1).replace("[[IMAGE_2]]",img2)
                if len(clean)>2000:return clean
            time.sleep(3)
        except:time.sleep(5)
    return None

def generate_title(news_title):
    """★ 제목 생성 개선 - AI 답변 필터링"""
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # ★ 더 명확한 프롬프트
    prompt=f"""
    다음 뉴스의 블로그 제목을 만드세요.
    
    뉴스: {news_title}
    
    규칙:
    - 제목만 출력 (설명 금지)
    - 20자 이내
    - 특수문자 금지
    - "제목을 만들어드릴게요" 같은 답변 금지
    
    제목:
    """
    
    try:
        res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=10)
        if res.status_code==200:
            title=res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            
            # ★ AI 답변 필터링
            if any(word in title for word in['드릴게','만들어','제공','다음과','입니다','니다','습니다']):
                # AI 답변이면 뉴스 제목 그대로 사용
                return news_title[:50]
            
            # 첫 줄만, 따옴표/별표 제거
            title=title.split('\n')[0].replace('"','').replace("'",'').replace('*','').replace('#','').strip()
            
            # ★ 너무 길면 자르기
            if len(title)>50:
                title=title[:50]
            
            return title if title else news_title[:50]
    except:
        pass
    return news_title[:50]

def run_bot():
    try:
        creds=Credentials.from_authorized_user_info(TOKEN_JSON)
        service=build('blogger','v3',credentials=creds)
        news_list=get_business_news_list()
        if not news_list:return
        target=None
        for news in news_list:
            if check_is_duplicate(service,news.title):continue
            target=news
            break
        if not target:return
        
        sources=collect_multiple_sources(target,news_list)
        synthesized=synthesize_sources(sources)if sources else None
        research_data=research_economy_deeply(target.title,synthesized)
        company_research=research_companies(synthesized)if synthesized else None
        company_data=[]
        if company_research:
            all_companies=company_research.get('us_companies',[])+company_research.get('kr_companies',[])
            company_data=get_company_info(all_companies)
        keywords=get_search_keywords(target.title)
        images=get_relevant_images_webp(keywords)
        dashboard=get_dashboard_html()
        content=generate_adsense_approved_content(target,images,dashboard,sources,synthesized,research_data,company_data)
        if not content:return
        title=generate_title(target.title)
        body={"kind":"blogger#post","title":title,"content":content}
        service.posts().insert(blogId=BLOG_ID,body=body).execute()
    except:
        import traceback
        traceback.print_exc()
        exit(1)

if __name__=="__main__":
    run_bot()
