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
        data = {"btc":{"price":res.get('bitcoin',{}).get('krw',0),"chg":res.get('bitcoin',{}).get('krw_24h_change',0),"name":"비트코인"},"eth":{"price":res.get('ethereum',{}).get('krw',0),"chg":res.get('ethereum',{}).get('krw_24h_change',0),"name":"이더리움"},"bnb":{"price":res.get('binancecoin',{}).get('krw',0),"chg":res.get('binancecoin',{}).get('krw_24h_change',0),"name":"바이낸스코인"},"xrp":{"price":res.get('ripple',{}).get('krw',0),"chg":res.get('ripple',{}).get('krw_24h_change',0),"name":"리플"},"ada":{"price":res.get('cardano',{}).get('krw',0),"chg":res.get('cardano',{}).get('krw_24h_change',0),"name":"카르다노"}}
    except:
        for key in ['btc','eth','bnb','xrp','ada']:
            data[key]={"price":0,"chg":0,"name":key.upper()}
    
    items=""
    for key in ['btc','eth','bnb','xrp','ada']:
        color,arrow=("#d63031","▲")if data[key]['chg']>=0 else("#0984e3","▼")
        items+=f'<div style="flex:1 1 18%;min-width:100px;margin:5px;padding:10px;background:#fff;border-radius:8px;text-align:center;"><div style="font-size:11px;color:#888;">{data[key]["name"]}</div><div style="font-size:14px;font-weight:800;color:{color};">{arrow} ₩{data[key]["price"]:,.0f}</div><div style="font-size:10px;color:{color};">({data[key]["chg"]:.2f}%)</div></div>'
    return f'<div style="margin-bottom:30px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);border-radius:12px;padding:15px;"><h3 style="text-align:center;margin:0 0 10px 0;font-size:16px;color:white;">🪙 암호화폐 시장</h3><div style="display:flex;flex-wrap:wrap;justify-content:center;gap:5px;">{items}</div></div>'

# 뉴스
def get_crypto_news_list():
    try:
        feed=feedparser.parse("https://news.google.com/rss/search?q=암호화폐+OR+비트코인+OR+알트코인+when:1d&hl=ko&gl=KR")
        if feed.entries:return feed.entries[:10]
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

# 여러 출처 수집
def collect_multiple_sources(target_news, all_news_list):
    sources = []
    target_keywords = set(target_news.title.split())
    content1 = fetch_article_content(target_news.link)
    if content1:
        sources.append({'title':target_news.title,'content':content1,'link':target_news.link})
    for news in all_news_list:
        if news.title != target_news.title and len(set(news.title.split()) & target_keywords) >= 2:
            content = fetch_article_content(news.link)
            if content:
                sources.append({'title':news.title,'content':content,'link':news.link})
                if len(sources) >= 4:break
    return sources

def synthesize_sources(sources):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    sources_text = "\n".join([f"[출처 {i+1}] {s['title']}\n{s['content'][:800]}" for i,s in enumerate(sources)])
    prompt = f"{sources_text}\n\n여러 암호화폐 뉴스 출처를 종합 분석. 공통점, 차이점, 숨겨진 맥락, 전문가 관점, 투자자 영향. 1500자 이상."
    try:
        res = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}]}, timeout=30)
        if res.status_code == 200:
            text = res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text) > 200:return text[:3000]
    except:pass
    return None

# 심층 리서치
def research_crypto_deeply(news_title, synthesized):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    context = synthesized[:1500] if synthesized else news_title
    prompt = f"{context}\n\n다음 각 4-5문장:\n1.blockchain_tech:블록체인 원리\n2.crypto_history:암호화폐 역사\n3.regulation:규제 환경\n4.market_sentiment:시장 심리\n5.future_outlook:미래 전망\n6.investment_risk:투자 리스크\nJSON 출력"
    try:
        res = requests.post(url, json={"contents":[{"parts":[{"text":prompt}]}]}, timeout=25)
        if res.status_code == 200:
            match = re.search(r'\{.*\}', res.json()['candidates'][0]['content']['parts'][0]['text'], re.DOTALL)
            if match:return json.loads(match.group())
    except:pass
    return None

# 코인 정보
def research_crypto_coins(synthesized):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    try:
        res = requests.post(url, json={"contents":[{"parts":[{"text":f"{synthesized[:1000]}\n\n관련 코인 2-3개 JSON:{{'coins':[{{'name':'Bitcoin','symbol':'BTC'}}]}}"}]}]}, timeout=15)
        if res.status_code == 200:
            match = re.search(r'\{.*\}', res.json()['candidates'][0]['content']['parts'][0]['text'], re.DOTALL)
            if match:return json.loads(match.group())
    except:pass
    return None

def get_coin_price_data(symbols):
    symbol_to_id={'BTC':'bitcoin','ETH':'ethereum','BNB':'binancecoin','XRP':'ripple','ADA':'cardano','SOL':'solana'}
    coin_data=[]
    for symbol in symbols[:3]:
        coin_id=symbol_to_id.get(symbol.upper(),symbol.lower())
        try:
            res=requests.get(f"https://api.coingecko.com/api/v3/coins/{coin_id}",timeout=10).json()
            coin_data.append({'name':res['name'],'symbol':res['symbol'].upper(),'price':f"₩{res['market_data']['current_price']['krw']:,.0f}",'market_cap':f"₩{res['market_data']['market_cap']['krw']/1e12:.2f}조",'change_24h':f"{res['market_data']['price_change_percentage_24h']:.2f}%",'rank':res['market_cap_rank']})
        except:continue
    return coin_data

def make_coin_cards(coin_data):
    if not coin_data:return ""
    cards='<div style="display:flex;flex-wrap:wrap;gap:15px;margin:25px 0;">'
    for c in coin_data:
        color="#d63031"if float(c['change_24h'].replace('%',''))>=0 else"#0984e3"
        cards+=f'<div style="flex:1 1 calc(50%-15px);min-width:250px;background:linear-gradient(135deg,#667eea22,#764ba233);border-radius:12px;padding:20px;border-left:4px solid #667eea;"><h3>{c["name"]}({c["symbol"]})</h3><p><b>순위:</b>#{c["rank"]}</p><p><b>현재가:</b>{c["price"]}</p><p><b>시총:</b>{c["market_cap"]}</p><p style="color:{color};"><b>24h:</b>{c["change_24h"]}</p></div>'
    cards+'</div>'
    return cards

# 키워드, 이미지
def get_search_keywords(news_title):
    try:
        res=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}",json={"contents":[{"parts":[{"text":f"'{news_title}' 영어 키워드 2개"}]}]},timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:return "cryptocurrency, blockchain"

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

# 초장문 칼럼
def generate_adsense_approved_content(news,images,dashboard,sources,synthesized,research_data,coin_data):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    sources_ref=""
    if sources:
        sources_ref="\n[참고 출처]\n"+"\n".join([f"{i+1}. {s['title']}" for i,s in enumerate(sources)])
    
    analysis_part=f"\n[종합 분석]\n{synthesized[:1500]}\n"if synthesized else""
    
    research_section=""
    if research_data:
        research_section=f"\n[전문 지식]\n-블록체인:{research_data.get('blockchain_tech','N/A')}\n-역사:{research_data.get('crypto_history','N/A')}\n-규제:{research_data.get('regulation','N/A')}\n-시장:{research_data.get('market_sentiment','N/A')}\n-미래:{research_data.get('future_outlook','N/A')}\n-리스크:{research_data.get('investment_risk','N/A')}"
    
    coin_summary=""
    if coin_data:
        coin_summary="\n[관련 코인]\n"+"\n".join([f"-{c['name']}({c['symbol']}):#{c['rank']},{c['price']}"for c in coin_data])
    
    prompt=f"""
    암호화폐 전문 애널리스트로 독창적 심층 칼럼 작성.
    
    [주제]{news.title}
    {sources_ref}
    {analysis_part}
    {research_section}
    {coin_summary}
    
    [애드센스 승인 조건]
    1.독창성:뉴스 요약 금지,전문가 재해석
    2.길이:2500자 이상
    3.부가가치:뉴스 없는 심층 분석
    4.다각도:찬반 양론
    5.실용성:투자자 도움
    6.출처 명시
    
    HTML:
    DASHBOARDHERE
    <div style="background:#fff3cd;padding:15px;border-left:4px solid #ffc107;margin:20px 0;">
    <strong>📌 편집자 주</strong><p>{len(sources)}개 출처 교차 분석, 블록체인 원리와 역사적 맥락을 더한 독창적 칼럼</p>
    </div>
    <h2>🔥 소제목</h2>
    <p>후킹 5문장</p>
    IMAGE1HERE
    <h2>📊 팩트 체크</h2>
    <p>핵심 사실 6문장</p>
    <ul><li>팩트1</li><li>팩트2</li><li>팩트3</li></ul>
    <h2>⛓️ 블록체인 기술 원리</h2>
    <p>기술 설명 8문장</p>
    <h2>📖 암호화폐의 역사</h2>
    <p>역사 비교 7문장</p>
    IMAGE2HERE
    <h2>⚖️ 규제 환경</h2>
    <p>각국 정책 7문장</p>
    <h2>🪙 주목할 코인</h2>
    <p>코인 분석 5문장</p>
    COINCARDSHERE
    <h2>⚖️ 찬성vs반대</h2>
    <p><strong>찬성:</strong>3문장</p>
    <p><strong>반대:</strong>3문장</p>
    <p><strong>제 생각:</strong>2문장</p>
    <h2>💰 투자자에게 미치는 영향</h2>
    <p>구체적 영향 6문장</p>
    <h2>🔮 미래 시나리오</h2>
    <p><strong>낙관:</strong>2문장</p>
    <p><strong>비관:</strong>2문장</p>
    <p><strong>현실:</strong>2문장</p>
    <h2>⚠️ 투자 리스크</h2>
    <p>위험 요소 5문장</p>
    <p><strong>결론:</strong>3문장</p>
    <hr>
    <div style="background:#f8f9fa;padding:15px;border-radius:8px;">
    <p><strong>📰 참고 출처</strong></p>
    {sources_ref.replace('[참고 출처]','').strip()}
    <p style="font-size:12px;color:#999;">본 칼럼은 독립 분석이며 투자 권유 아님</p>
    </div>
    
    규칙:HTML만,해요체,5문장 이상/섹션
    """
    
    for attempt in range(3):
        try:
            res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=50)
            if res.status_code==200:
                clean=clean_markdown(res.json()['candidates'][0]['content']['parts'][0]['text']).replace("```html","").replace("```","").strip()
                clean=clean.replace("DASHBOARDHERE",dashboard).replace("[[DASHBOARD]]",dashboard)
                clean=clean.replace("COINCARDSHERE",make_coin_cards(coin_data)).replace("[[COIN_CARDS]]",make_coin_cards(coin_data))
                img1=f'<img src="{images[0]}" style="width:100%;border-radius:12px;margin:25px 0;">'if len(images)>0 else""
                img2=f'<img src="{images[1]}" style="width:100%;border-radius:12px;margin:25px 0;">'if len(images)>1 else img1
                clean=clean.replace("IMAGE1HERE",img1).replace("IMAGE2HERE",img2).replace("[[IMAGE_1]]",img1).replace("[[IMAGE_2]]",img2)
                if len(clean)>2000:return clean
            time.sleep(3)
        except Exception as e:
            time.sleep(5)
    return None

def generate_title(news_title):
    try:
        res=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}",json={"contents":[{"parts":[{"text":f"'{news_title}' 전문가 칼럼 제목 1개"}]}]},timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')[0].replace('"','').replace('*','')
    except:return news_title

# 메인
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
        if coin_research and 'coins' in coin_research:
            coin_data=get_coin_price_data([c['symbol']for c in coin_research['coins']])
        keywords=get_search_keywords(target.title)
        images=get_relevant_images_webp(keywords)
        dashboard=get_crypto_dashboard_html()
        content=generate_adsense_approved_content(target,images,dashboard,sources,synthesized,research_data,coin_data)
        if not content:return
        title=generate_title(target.title)
        body={"kind":"blogger#post","title":title,"content":content}
        service.posts().insert(blogId=BLOG_ID,body=body).execute()
    except Exception as e:
        import traceback
        traceback.print_exc()
        exit(1)

if __name__=="__main__":
    run_bot()
