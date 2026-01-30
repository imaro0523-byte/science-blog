import os
import json
import time
import requests
import feedparser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# =========================================================
# [설정 구역] GitHub Secrets 가져오기
# =========================================================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BLOG_ID = os.environ.get('MONEY_BLOG_ID') # 머니 블로그 ID 확인
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')

try:
    client_env = os.environ.get('CLIENT_JSON')
    token_env = os.environ.get('TOKEN_JSON')
    
    if not client_env or not token_env or not PEXELS_API_KEY:
        raise ValueError("GitHub Secrets 필수 값 누락")
        
    CLIENT_JSON = json.loads(client_env)
    TOKEN_JSON = json.loads(token_env)
except Exception as e:
    print(f"⛔ 설정 로딩 에러: {e}")
    exit(1)

MODEL_NAME = "gemini-2.5-flash"

# =========================================================
# [함수 1] 대시보드 데이터 생성 (누락된 기능 복구)
# =========================================================
def get_dashboard_html():
    print("📊 시장 데이터(코인/공포지수) 수집 중...")
    btc, btc_chg, fng, fng_class = 0, 0, 0, "Unknown"
    
    # 1. CoinGecko (비트코인 가격)
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=krw&include_24hr_change=true"
        res = requests.get(url, timeout=5).json()
        btc = res['bitcoin']['krw']
        btc_chg = res['bitcoin']['krw_24h_change']
    except:
        pass

    # 2. Alternative.me (공포/탐욕 지수)
    try:
        fng_res = requests.get("https://api.alternative.me/fng/", timeout=5).json()
        fng = int(fng_res['data'][0]['value'])
        fng_class = fng_res['data'][0]['value_classification']
    except:
        pass

    # HTML 생성
    btc_color = "red" if btc_chg >= 0 else "blue"
    btc_arrow = "▲" if btc_chg >= 0 else "▼"
    
    fng_emoji = "😐"
    if fng >= 75: fng_emoji = "🔥 극단적 탐욕 (매도 주의)"
    elif fng >= 55: fng_emoji = "😋 탐욕 (불장)"
    elif fng <= 25: fng_emoji = "🥶 극단적 공포 (저점 매수?)"
    elif fng <= 45: fng_emoji = "😨 공포"

    html = f"""
    <div style="background: #f8f9fa; border: 2px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 25px; font-family: sans-serif;">
        <h3 style="text-align:center; margin:0 0 10px 0; color:#333;">🚀 실시간 머니 브리핑</h3>
        <div style="display:flex; justify-content:space-around; text-align:center;">
            <div>
                <div style="font-size:12px; color:#555;">비트코인 (BTC)</div>
                <div style="color:{btc_color}; font-weight:bold; font-size:16px;">{btc_arrow} {btc:,.0f}원 <br><small>({btc_chg:.2f}%)</small></div>
            </div>
            <div>
                <div style="font-size:12px; color:#555;">공포/탐욕 지수</div>
                <div style="font-weight:bold; font-size:16px;">{fng}점 <br><small>{fng_emoji}</small></div>
            </div>
        </div>
    </div>
    """
    return html

# =========================================================
# [함수 2] 금융경제 뉴스 리스트 가져오기
# =========================================================
def get_tech_news_list():
    print("🔍 구글 뉴스 [금융] 섹션 헤드라인 검색...")
    rss_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            top_5_news = feed.entries[:5]
            print(f"✅ 총 {len(top_5_news)}개의 최신 뉴스를 가져왔습니다.")
            return top_5_news
    except Exception as e:
        print(f"⛔ 뉴스 검색 에러: {e}")
    return []

# =========================================================
# [함수 3] 중복 포스팅 확인 함수
# =========================================================
def check_is_duplicate(service, news_title):
    try:
        posts = service.posts().list(blogId=BLOG_ID, maxResults=10).execute()
        items = posts.get('items', [])
        for post in items:
            if news_title in post.get('content', ''):
                return True
        return False
    except Exception as e:
        print(f"⚠️ 중복 확인 중 에러 (진행함): {e}")
        return False

# =========================================================
# [함수 4] 키워드 추출
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"뉴스 제목: '{news_title}'. 이 뉴스의 핵심 '영어' 경제 키워드 3개를 콤마로 구분해줘. (예: Bitcoin, Stock, Gold)"
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "money, business"

# =========================================================
# [함수 5] 이미지 검색 (URL 에러 수정 완료)
# =========================================================
def get_relevant_images_webp(query):
    print(f"🖼️ Pexels 이미지 검색: {query}")
    try:
        # URL에 마크다운이나 대괄호가 들어가지 않도록 주의
        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": PEXELS_API_KEY}
        params = {"query": query, "per_page": 2, "orientation": "landscape", "size": "medium"}
        
        resp = requests.get(url, headers=headers, params=params)
        
        if resp.status_code == 200:
            urls = [p['src']['original'] + "?auto=compress&fm=webp&w=800" for p in resp.json().get('photos', [])]
            if len(urls) >= 1:
                print(f"✅ 이미지 {len(urls)}장 확보")
                return urls
            else:
                return []
        else:
            print(f"⚠️ 이미지 검색 실패 Code: {resp.status_code}")
            return []
    except Exception as e:
        print(f"⛔ 이미지 검색 에러: {e}")
    return []

# =========================================================
# [함수 6] 후킹 제목 생성
# =========================================================
def generate_viral_title(news_title):
    print("🎣 AI가 클릭을 유도하는 제목을 짓고 있습니다...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    너는 100만 유튜버이자 투자 전문가야. 아래 뉴스를 사람들이 보자마자 
    '이거 안 읽으면 손해 보겠다'는 생각이 들게 강력한 제목으로 뽑아줘.
    
    [원래 제목]: {news_title}
    
    [규칙]
    1. 도발적인 질문이나 강렬한 단어 사용 (폭등, 폭락, 비밀, 골든타임, 마지막 기회 등).
    2. 괄호 '()' 안에 핵심 종목이나 키워드 삽입.
    3. 반말 말고 정중하지만 긴박한 말투.
    
    [출력]: 제목 한 줄만.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.7}}
    
    try:
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        if res.status_code == 200:
            new_title = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            return new_title.replace('"', '').replace("'", "")
    except:
        pass
    return news_title

# =========================================================
# [함수 7] 글 작성 (프롬프트 유지 & 변수 매칭 수정)
# =========================================================
def generate_deep_content_with_images(news, image_urls, dashboard_html):
    print(f"🧠 AI({MODEL_NAME})가 경제 리뷰를 작성 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # 이미지 태그 생성 (프롬프트의 {img_tag}와 매칭)
    img_tag = ""
    if len(image_urls) > 0:
        img_tag = f'<img src="{image_urls[0]}" alt="Money Image" style="width:100%; border-radius:10px; margin:20px 0;">'
    
    prompt = f"""
    당신은 냉철한 투자 전문가입니다. 아래 뉴스에 대한 분석글을 HTML로 작성하세요.

    [뉴스]: {news.title}
    [링크]: {news.link}
    
    [글 구조 HTML]
    1. {dashboard_html} (이건 내가 넣어준 HTML이니까 그대로 제일 위에 출력해줘)
    2. <p> (도입부: 독자의 욕망을 자극. "지금 기회를 놓치면 후회합니다" 톤)</p>
    3. {img_tag}
    4. <h2>팩트 체크: 돈의 흐름이 바뀐다</h2>
    5. <p> (뉴스 분석: 세력들의 의도와 시장 반응)</p>
    6. <h2>투자 전략: 그래서 살까 말까?</h2>
    7. <p> (대응 전략: 공격적인 투자자라면? 보수적인 투자자라면?)</p>
    8. <p style="color: grey; font-size: 0.8em;">(주의: 이 글은 투자 조언이 아니며, 모든 투자의 책임은 본인에게 있습니다.)</p>
    
    [필수] 
    - HTML 태그만 출력. 
    - 마크다운(```html) 금지.
    - 대시보드 HTML 코드는 변형하지 말고 그대로 맨 위에 넣어.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3}}
    
    for _
