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
BLOG_ID=os.environ.get('BLOG_ID')
if not GEMINI_API_KEY or not BLOG_ID:exit(1)
try:
    CLIENT_JSON=json.loads(os.environ.get('CLIENT_JSON','{}'))
    TOKEN_JSON=json.loads(os.environ.get('TOKEN_JSON','{}'))
except:exit(1)
MODEL_NAME = "gemini-3-flash-preview"

def get_science_news_list():
    try:
        feed=feedparser.parse("https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=ko&gl=KR&ceid=KR:ko")
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
    prompt=f"{sources_text}\n\n여러 과학 뉴스 종합. 공통점,차이점,숨겨진 맥락,과학적 의미. 1500자 이상"
    try:
        res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=30)
        if res.status_code==200:
            text=res.json()['candidates'][0]['content']['parts'][0]['text']
            if len(text)>200:return text[:3000]
    except:pass
    return None

def research_science_deeply(news_title,synthesized):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    context=synthesized[:1500]if synthesized else news_title
    prompt=f"{context}\n\n다음 각 4-5문장:\n1.scientific_principle:과학 원리\n2.research_method:연구 방법\n3.historical_context:역사\n4.academic_evaluation:학계 평가\n5.future_application:미래 응용\n6.limitations:한계\nJSON"
    try:
        res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=25)
        if res.status_code==200:
            match=re.search(r'\{.*\}',res.json()['candidates'][0]['content']['parts'][0]['text'],re.DOTALL)
            if match:return json.loads(match.group())
    except:pass
    return None

def get_search_keywords(news_title):
    try:
        res=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}",json={"contents":[{"parts":[{"text":f"'{news_title}' 영어 키워드 2개"}]}]},timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:return"science,research"

def get_relevant_images_webp(query):
    if not PEXELS_API_KEY:return[]
    try:
        resp=requests.get("https://api.pexels.com/v1/search",headers={"Authorization":PEXELS_API_KEY},params={"query":query,"per_page":2},timeout=10)
        if resp.status_code==200:return[p['src']['original']+"?w=800"for p in resp.json().get('photos',[])]
    except:pass
    return[]

def clean_markdown(text):
    text=re.sub(r'\*\*([^\*]+)\*\*',r'<strong>\1</strong>',text)
    text=re.sub(r'\*([^\*]+)\*',r'<em>\1</em>',text)
    text=text.replace('###','').replace('##','').replace('```','').replace('**','')
    text=re.sub(r'<i>(\d+)</i>',r'\1',text)
    return re.sub(r'</i>|<i>','',text)

def generate_adsense_approved_content(news,images,sources,synthesized,research_data):
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    sources_ref=""
    if sources:sources_ref="\n[참고]\n"+"\n".join([f"{i+1}.{s['title']}"for i,s in enumerate(sources)])
    analysis_part=f"\n[종합]\n{synthesized[:1500]}\n"if synthesized else""
    research_section=""
    if research_data:
        research_section=f"\n[지식]\n-원리:{research_data.get('scientific_principle','N/A')}\n-방법:{research_data.get('research_method','N/A')}\n-역사:{research_data.get('historical_context','N/A')}\n-평가:{research_data.get('academic_evaluation','N/A')}\n-응용:{research_data.get('future_application','N/A')}\n-한계:{research_data.get('limitations','N/A')}"
    
    prompt=f"""
    과학 저널리스트로 독창적 칼럼.
    
    [주제]{news.title}
    {sources_ref}
    {analysis_part}
    {research_section}
    
    [애드센스]
    1.독창성:뉴스 요약 금지
    2.길이:2500자+
    3.부가가치:심층 분석
    4.다각도:찬반
    5.실용성:독자 도움
    6.출처
    
    HTML:
    <div style="background:#fff3cd;padding:15px;border-left:4px solid #ffc107;margin:20px 0;">
    <strong>📌 편집자 주</strong><p>{len(sources)}개 출처 교차 분석, 과학 원리와 역사 더한 독창 칼럼</p>
    </div>
    <h2>🔥 소제목</h2>
    <p>후킹 5문장</p>
    IMAGE1HERE
    <h2>📊 팩트</h2>
    <p>사실 6문장</p>
    <ul><li>팩트1</li><li>팩트2</li><li>팩트3</li></ul>
    <h2>🔬 과학 원리</h2>
    <p>원리 8문장</p>
    <h2>🧪 연구 방법</h2>
    <p>방법론 7문장</p>
    IMAGE2HERE
    <h2>📖 과학사</h2>
    <p>역사 7문장</p>
    <h2>⚖️ 찬성vs반대</h2>
    <p><strong>찬성:</strong>3문장</p>
    <p><strong>반대:</strong>3문장</p>
    <p><strong>제 생각:</strong>2문장</p>
    <h2>🚀 미래 응용</h2>
    <p>응용 6문장</p>
    <h2>🔮 시나리오</h2>
    <p><strong>낙관:</strong>2문장</p>
    <p><strong>비관:</strong>2문장</p>
    <p><strong>현실:</strong>2문장</p>
    <h2>⚠️ 한계</h2>
    <p>한계 5문장</p>
    <p><strong>결론:</strong>3문장</p>
    <hr>
    <div style="background:#f8f9fa;padding:15px;">
    <p><strong>📰 출처</strong></p>
    {sources_ref.replace('[참고]','').strip()}
    <p style="font-size:12px;color:#999;">독립 분석</p>
    </div>
    
    규칙:HTML,해요체,5문장+
    """
    
    for attempt in range(3):
        try:
            res=requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}]},timeout=50)
            if res.status_code==200:
                clean=clean_markdown(res.json()['candidates'][0]['content']['parts'][0]['text']).replace("```html","").replace("```","").strip()
                img1=f'<img src="{images[0]}" style="width:100%;border-radius:12px;margin:25px 0;">'if len(images)>0 else""
                img2=f'<img src="{images[1]}" style="width:100%;border-radius:12px;margin:25px 0;">'if len(images)>1 else img1
                clean=clean.replace("IMAGE1HERE",img1).replace("IMAGE2HERE",img2).replace("[[IMAGE_1]]",img1).replace("[[IMAGE_2]]",img2)
                if len(clean)>2000:return clean
            time.sleep(3)
        except:time.sleep(5)
    return None

def generate_title(news_title):
    try:
        res=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}",json={"contents":[{"parts":[{"text":f"'{news_title}' 전문가 칼럼 제목 1개"}]}]},timeout=10)
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')[0].replace('"','').replace('*','')
    except:return news_title

def run_bot():
    try:
        creds=Credentials.from_authorized_user_info(TOKEN_JSON)
        service=build('blogger','v3',credentials=creds)
        news_list=get_science_news_list()
        if not news_list:return
        target=None
        for news in news_list:
            if check_is_duplicate(service,news.title):continue
            target=news
            break
        if not target:return
        
        sources=collect_multiple_sources(target,news_list)
        synthesized=synthesize_sources(sources)if sources else None
        research_data=research_science_deeply(target.title,synthesized)
        keywords=get_search_keywords(target.title)
        images=get_relevant_images_webp(keywords)
        content=generate_adsense_approved_content(target,images,sources,synthesized,research_data)
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
