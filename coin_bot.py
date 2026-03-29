import os
import json
import time
import re
import requests
import feedparser
import trafilatura
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

GEMINI_API_KEY=os.environ.get('GEMINI_API_KEY')
PEXELS_API_KEY=os.environ.get('PEXELS_API_KEY')
BLOG_ID = os.environ.get('CRYPTO_BLOG_ID') or os.environ.get('BLOG_ID')
if not GEMINI_API_KEY or not BLOG_ID:exit(1)
try:
    CLIENT_JSON=json.loads(os.environ.get('CLIENT_JSON','{}'))
    TOKEN_JSON=json.loads(os.environ.get('TOKEN_JSON','{}'))
except:exit(1)
MODEL_NAME = "gemini-2.5-flash"

def get_crypto_dashboard_html():
    data={}
    try:
        res=requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,binancecoin,ripple,cardano&vs_currencies=krw&include_24hr_change=true",timeout=10).json()
        data={"btc":{"price":res.get('bitcoin',{}).get('krw',0),"chg":res.get('bitcoin',{}).get('krw_24h_change',0),"name":"비트코인"},"eth":{"price":res.get('ethereum',{}).get('krw',0),"chg":res.get('ethereum',{}).get('krw_24h_change',0),"name":"이더리움"},"bnb":{"price":res.get('binancecoin',{}).get('krw',0),"chg":res.get('binancecoin',{}).get('krw_24h_change',0),"name":"바이낸스"},"xrp":{"price":res.get('ripple',{}).get('krw',0),"chg":res.get('ripple',{}).get('krw_24h_change',0),"name":"리플"},"ada":{"price":res.get('cardano',{}).get('krw',0),"chg":res.get('cardano',{}).get('krw_24h_change',0),"name":"카르다노"}}
    except:
        for key in ['btc','eth','bnb','xrp','ada']:
            data[key]={"price":0,"chg":0,"name":key.upper()}
    items=""
    for key in ['btc','eth','bnb','xrp','ada']:
        color,arrow=("#d63031","▲")if data[key]['chg']>=0 else("#0984e3","▼")
        items+=f'<div style="flex:1 1 18%;min-width:100px;margin:5px;padding:10px;background:#fff;border-radius:8px;text-align:center;"><div style="font-size:11px;color:#888;">{data[key]["name"]}</div><div style="font-size:14px;font-weight:800;color:{color};">{arrow} ₩{data[key]["price"]:,.0f}</div><div style="font-size:10px;color:{color};">({data[key]["chg"]:.2f}%)</div></div>'
    return f'<div style="margin-bottom:30px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);border-radius:12px;padding:15px;"><h3 style="text-align:center;margin:0 0 10px 0;font-size:16px;color:white;">🪙 암호화폐 시장</h3><div style="display:flex;flex-wrap:wrap;justify-content:center;gap:5px;">{items}</div></div>'

def get_crypto_news_list():
    try:
        feed=feedparser.parse("https://news.google.com/rss/search?q=암호화폐+OR+비트코인+OR+알트코인+OR+블록체인+when:1d&hl=ko&gl=KR")
        if feed.entries:return feed.entries[:12]
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
    prompt=f"{sources_text}\n\n여러 암호화폐 뉴스 종합. 공통점,차이점,숨겨진 맥락,전문가 관점,투자자 영향. 1500자+"
    try:
        res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=30)
        if res.status_code==200:
            text=res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text)>200:return text[:3000]
    except:pass
    return None

# ★ 개선: 매번 같은 내용 반복 방지
def research_crypto_deeply(news_title,synthesized):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    context=synthesized[:1500]if synthesized else news_title
    
    prompt=f"""
    {context}
    
    다음 항목을 각 4-5문장으로 (일반론 금지, 이 뉴스만의 특징 분석):
    
    1. blockchain_tech: 이 뉴스와 관련된 구체적 블록체인 기술 (일반론 금지)
    2. regulation: 현재 규제 이슈 (미국/한국/중국 등 구체적)
    3. market_sentiment: 지금 시장 심리 (Fear&Greed, 온체인, 고래)
    4. trending_coins: 최근 해외 화제 코인 (구체적 이름)
    5. coin_vision: 관련 코인의 비전/목표 (백서 기반)
    6. roadmap: 앞으로의 업데이트 계획/마일스톤
    7. dominance: BTC 도미넌스, 시가총액 순위 변화
    8. investment_risk: 투자 리스크 (구체적)
    
    JSON:
    {{"blockchain_tech":"...","regulation":"...","market_sentiment":"...","trending_coins":"...","coin_vision":"...","roadmap":"...","dominance":"...","investment_risk":"..."}}
    """
    
    try:
        res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=30)
        if res.status_code==200:
            match=re.search(r'\{.*\}',res.json()['candidates'][0]['content']['parts'][0]['text'],re.DOTALL)
            if match:return json.loads(match.group())
    except:pass
    return None

# ★ 간소화: 백서는 research_crypto_deeply에 통합
def research_crypto_coins(synthesized):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    try:
        res=requests.post(url,json={"contents":[{"parts":[{"text":f"{synthesized[:1000]}\n\n관련 코인 2-3개 JSON:{{'coins':[{{'name':'Bitcoin','symbol':'BTC'}}]}}"}]}]},timeout=15)
        if res.status_code==200:
            match=re.search(r'\{.*\}',res.json()['candidates'][0]['content']['parts'][0]['text'],re.DOTALL)
            if match:return json.loads(match.group())
    except:pass
    return None

def get_coin_price_data(symbols):
    symbol_to_id={'BTC':'bitcoin','ETH':'ethereum','BNB':'binancecoin','XRP':'ripple','ADA':'cardano','SOL':'solana','DOT':'polkadot','DOGE':'dogecoin','MATIC':'matic-network','LINK':'chainlink','AVAX':'avalanche-2','UNI':'uniswap'}
    coin_data=[]
    for symbol in symbols[:3]:
        coin_id=symbol_to_id.get(symbol.upper(),symbol.lower())
        try:
            res=requests.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}",timeout=10).json()
            coin_data.append({'name':res['name'],'symbol':res['symbol'].upper(),'price':f"₩{res['market_data']['current_price']['krw']:,.0f}",'market_cap':f"₩{res['market_data']['market_cap']['krw']/1e12:.2f}조",'change_24h':f"{res['market_data']['price_change_percentage_24h']:.2f}%",'rank':res['market_cap_rank']})
        except:continue
    return coin_data

def make_coin_cards(coin_data):
    if not coin_data:return""
    cards='<div style="display:flex;flex-wrap:wrap;gap:15px;margin:25px 0;">'
    for c in coin_data:
        color="#d63031"if float(c['change_24h'].replace('%',''))>=0 else"#0984e3"
        cards+=f'<div style="flex:1 1 calc(50%-15px);min-width:250px;background:linear-gradient(135deg,#667eea22,#764ba233);border-radius:12px;padding:20px;border-left:4px solid #667eea;"><h3 style="margin:0 0 10px 0;">{c["name"]}({c["symbol"]})</h3><p style="margin:5px 0;font-size:13px;"><b>순위:</b>#{c["rank"]}</p><p style="margin:5px 0;font-size:13px;"><b>현재가:</b>{c["price"]}</p><p style="margin:5px 0;font-size:13px;"><b>시총:</b>{c["market_cap"]}</p><p style="margin:5px 0;font-size:13px;color:{color};"><b>24h:</b>{c["change_24h"]}</p></div>'
    cards+='</div>'
    return cards

def get_search_keywords(news_title):
    try:
        res=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}",json={"contents":[{"parts":[{"text":f"'{news_title}' 영어 키워드 2개"}]}]},timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:return"cryptocurrency,blockchain"

def get_relevant_images_webp(query):
    if not PEXELS_API_KEY:return[]
    try:
        resp=requests.get("https://api.pexels.com/v1/search",headers={"Authorization":PEXELS_API_KEY},params={"query":query,"per_page":2},timeout=10)
        if resp.status_code==200:return[p['src']['original']+"?w=800"for p in resp.json().get('photos',[])]
    except:pass
    return[]

def clean_markdown(text):
    text=re.sub(r'^[A-Z]{3,5}\s*\n','',text)  # ★ HDMR 제거
    text=re.sub(r'\*\*([^\*]+)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'\*([^\*]+)\*',r'<em>\1</em>',text)
    text=text.replace('###','').replace('##','').replace('```','').replace('**','')
    text=re.sub(r'<i>(\d+)</i>',r'\1',text)
    text=re.sub(r'</i>|<i>','',text)
    return text.strip()

def generate_premium_crypto_content(news,images,dashboard,sources,synthesized,research_data,coin_data):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # ★ 편집자 주 조건부
    editor_note=""
    if sources and len(sources)>=2:
        editor_note=f'<div style="background:#fff3cd;padding:15px;border-left:4px solid #ffc107;margin:20px 0;"><strong>📌 편집자 주</strong><p style="margin:5px 0 0 0;font-size:14px;">이 글은 {len(sources)}개 출처를 교차 분석한 독창적 칼럼입니다.</p></div>'
    
    sources_ref=""
    if sources:sources_ref="\n[참고]\n"+"\n".join([f"{i+1}.{s['title']}"for i,s in enumerate(sources)])
    analysis_part=f"\n[종합]\n{synthesized[:1500]}\n"if synthesized else""
    research_section=""
    if research_data:
        research_section=f"\n[지식]\n-기술:{research_data.get('blockchain_tech','N/A')}\n-규제:{research_data.get('regulation','N/A')}\n-시장:{research_data.get('market_sentiment','N/A')}\n-화제:{research_data.get('trending_coins','N/A')}\n-비전:{research_data.get('coin_vision','N/A')}\n-로드맵:{research_data.get('roadmap','N/A')}\n-도미넌스:{research_data.get('dominance','N/A')}\n-리스크:{research_data.get('investment_risk','N/A')}"
    coin_summary=""
    if coin_data:coin_summary="\n[코인]\n"+"\n".join([f"-{c['name']}({c['symbol']}):#{c['rank']},{c['price']}"for c in coin_data])
    
    prompt=f"""
    암호화폐 애널리스트로 독창적 칼럼.
    
    [주제]{news.title}
    {sources_ref}
    {analysis_part}
    {research_section}
    {coin_summary}
    
    [중요] 매번 반복되는 일반론 금지!
    - "비트코인은 2009년..." 같은 뻔한 역사 금지
    - "블록체인은 분산원장..." 같은 교과서 설명 금지
    - 이 뉴스만의 특징, 지금 이슈만 집중
    
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
    <h2>⛓️ 기술 포인트</h2>
    <p>이 뉴스의 기술 7문장</p>
    <h2>⚖️ 규제 이슈</h2>
    <p>현재 규제 6문장</p>
    IMAGE2HERE
    <h2>🔥 화제 코인</h2>
    <p>트렌딩 5문장</p>
    COINCARDSHERE
    <h2>🎯 코인 비전</h2>
    <p>목표/비전 5문장</p>
    <h2>🗓️ 로드맵</h2>
    <p>업데이트 계획 5문장</p>
    <h2>📊 도미넌스</h2>
    <p>시총 순위 변화 4문장</p>
    <h2>⚖️ 찬성vs반대</h2>
    <p><strong>찬성:</strong>3문장</p>
    <p><strong>반대:</strong>3문장</p>
    <p><strong>제 분석:</strong>2문장</p>
    <h2>💰 투자자 영향</h2>
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
    <p style="font-size:12px;color:#999;">독립 분석, DYOR</p>
    </div>
    
    규칙:HTML,해요체,5문장+
    """
    
    for attempt in range(3):
        try:
            res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=50)
            if res.status_code==200:
                clean=clean_markdown(res.json()['candidates'][0]['content']['parts'][0]['text']).replace("```html","").replace("```","").strip()
                clean=clean.replace("DASHBOARDHERE",dashboard).replace("[[DASHBOARD]]",dashboard)
                clean=clean.replace("EDITORHERE",editor_note).replace("[[EDITOR]]",editor_note)
                clean=clean.replace("COINCARDSHERE",make_coin_cards(coin_data)).replace("[[COIN_CARDS]]",make_coin_cards(coin_data))
                img1=f'<img src="{images[0]}" style="width:100%;border-radius:12px;margin:25px 0;">'if len(images)>0 else""
                img2=f'<img src="{images[1]}" style="width:100%;border-radius:12px;margin:25px 0;">'if len(images)>1 else img1
                clean=clean.replace("IMAGE1HERE",img1).replace("IMAGE2HERE",img2).replace("[[IMAGE_1]]",img1).replace("[[IMAGE_2]]",img2)
                if len(clean)>2000:return clean
            time.sleep(3)
        except:time.sleep(5)
    return None

def generate_title(news_title):
    """★ 제목 생성 개선"""
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt=f"다음 뉴스의 블로그 제목만 출력 (설명 금지, 20자 이내):\n{news_title}\n\n제목:"
    try:
        res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=10)
        if res.status_code==200:
            title=res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            if any(word in title for word in['드릴게','만들어','제공','다음과','입니다','니다','습니다']):
                return news_title[:50]
            title=title.split('\n')[0].replace('"','').replace("'",'').replace('*','').replace('#','').strip()
            if len(title)>50:title=title[:50]
            return title if title else news_title[:50]
    except:pass
    return news_title[:50]

def run_bot():
    try:
        creds=Credentials.from_authorized_user_info(TOKEN_JSON)
        service=build('blogger','v3',credentials=creds)
        news_list=get_crypto_news_list()
        if not news_list:return
        target=None
        for news in news_list:
            if check_is_duplicate(service,news.title):continue
            target=news
            break
        if not target:return
        
        sources=collect_multiple_sources(target,news_list)
        synthesized=synthesize_sources(sources)if sources else None
        research_data=research_crypto_deeply(target.title,synthesized)
        coin_research=research_crypto_coins(synthesized)if synthesized else None
        coin_data=[]
        if coin_research and'coins'in coin_research:
            coin_data=get_coin_price_data([c['symbol']for c in coin_research['coins']])
        keywords=get_search_keywords(target.title)
        images=get_relevant_images_webp(keywords)
        dashboard=get_crypto_dashboard_html()
        content=generate_premium_crypto_content(target,images,dashboard,sources,synthesized,research_data,coin_data)
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
