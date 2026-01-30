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
BLOG_ID = os.environ.get('MONEY_BLOG_ID')  # 머니 블로그 ID
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')

# 환경변수 로딩 및 에러 처리
try:
    client_env = os.environ.get('CLIENT_JSON')
    token_env = os.environ.get('TOKEN_JSON')
    
    if not client_env or not token_env or not PEXELS_API_KEY:
        # 로컬 테스트가 아닐 경우에만 에러 발생
        if not os.path.exists('client_secret.json'): 
             print("⚠️ 주의: 환경변수가 일부 누락되었습니다.")
        
    CLIENT_JSON = json.loads(client_env) if client_env else {}
    TOKEN_JSON = json.loads(token_env) if token_env else {}
except Exception as e:
    print(f"⛔ 설정 로딩 에러: {e}")
    # 일단 진행해보고 실패하면 멈춤

MODEL_NAME = "gemini-2.5-flash"

# =========================================================
# [함수 1] 대시보드 데이터 생성 (HTML 생성기)
# =========================================================
def get_dashboard_html():
    print("📊 시장 데이터 수집 중...")
    btc, btc_chg, fng = 0, 0, 0
    
    # 1. CoinGecko (비트코인)
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=krw&include_24hr_change=true"
        res = requests.get(url, timeout=5).json()
        btc = res['bitcoin']['krw']
        btc_chg = res['bitcoin']['krw_24h_change']
    except:
        pass

    # 2. Alternative.me (공포지수)
    try:
        fng_res = requests.get("https://api.alternative.me/fng/", timeout=5).json()
        fng = int(fng_res['data'][0]['value'])
    except:
        pass

    # HTML 조립
    btc_color = "red" if btc_chg >= 0 else "blue"
    btc_arrow = "▲" if btc_chg >= 0 else "▼"
    
    fng_emoji = "😐"
    if fng >= 75: fng_emoji = "🔥 탐욕"
    elif fng <= 25: fng_emoji = "🥶 공포"

    # 중괄호 충돌 방지를 위해 CSS는 인라인으로 단순화
    html = f"""
    <div style="background: #f8f9fa; border: 2px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 25px; font-family: sans-serif;">
        <h3 style="text-align:center; margin:0 0 10px 0; color:#333;">🚀 머니 브리핑</h3>
        <div style="display:flex; justify-content:space-around; text-align:center;">
            <div>
                <div style="font-size:12px; color:#555;">비트코인</div>
                <div style="color:{btc_color}; font-weight:bold; font-size:16px;">{btc_arrow} {btc:,.0f}원</div>
            </div>
            <div>
                <div style="font-size:12px; color:#555;">공포지수</div>
                <div style="font-weight:bold; font-size:16px;">{fng}점 {fng_emoji}</div>
            </div>
        </div>
    </div>
    <br>
    """
    return html

# =========================================================
# [함수 2] 금융경제 뉴스 리스트 가져오기
# =========================================================
def get_tech_news_list():
    print("🔍 구글 뉴스 [금융] 섹션 검색...")
    rss_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            top_5_news = feed.entries[:5]
            print(f"✅ 뉴스 {len(top_5_news)}개 가져옴")
            return top_5_news
    except Exception as e:
        print(f"⛔ 뉴스 검색 에러: {e}")
    return []

# =========================================================
# [함수 3] 중복 포스팅 확인
# =========================================================
def check_is_duplicate(service, news_title):
    try:
        posts = service.posts().list(blogId=BLOG_ID, maxResults=10).execute()
        for post in posts.get('items', []):
            if news_title in post.get('content', ''):
                return True
        return False
    except Exception as e:
        print(f"⚠️ 중복 확인 패스 (에러): {e}")
        return False

# =========================================================
# [함수 4] 키워드 추출
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"뉴스 제목: '{news_title}'. 핵심 영어 키워드 3개만 콤마로 구분해. (예: Bitcoin, Economy)"
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "money, business"

# =========================================================
# [함수 5] 이미지 검색 (안전한 버전)
# =========================================================
def get_relevant_images_webp(query):
    print(f"🖼️ 이미지 검색: {query}")
    try:
        api_url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": PEXELS_API_KEY}
        params = {"query": query, "per_page": 2, "orientation": "landscape", "size": "medium"}
        
        resp = requests.get(api_url, headers=headers, params=params)
        if resp.status_code == 200:
            urls = [p['src']['original'] + "?auto=compress&fm=webp&w=800" for p in resp.json().get('photos', [])]
            print(f"✅ 이미지 {len(urls)}장 확보")
            return urls
        else:
            print(f"⚠️ 이미지 검색 실패 Status: {resp.status_code}")
            return []
    except Exception as e:
        print(f"⛔ 이미지 검색 에러: {e}")
    return []

# =========================================================
# [함수 6] 본문 작성 (치환 방식 적용)
# =========================================================
def generate_content_safe(news, image_urls, dashboard_html):
    print(f"🧠 AI가 글을 작성합니다...")
    
    img_tag = ""
    if image_urls:
        img_tag = f'<img src="{image_urls[0]}" alt="Money Image" style="width:100%; border-radius:10px; margin:20px 0;">'
    
    # ★ 핵심: 대시보드 HTML을 프롬프트에 넣지 않고, [[DASHBOARD]] 자리만 비워둠
    prompt = f"""
    투자 전문가 페르소나로 글을 작성해.
    
    [뉴스]: {news.title}
    [링크]: {news.link}
    
    [출력 포맷 - HTML]
    1. 맨 첫 줄에 정확히 [[DASHBOARD]] 라고만 적어. (나중에 내가 표를 넣을 곳임)
    2. <p> (도입부: "지금 놓치면 후회합니다" 같은 강렬한 훅)</p>
    3. {img_tag} (이 이미지 태그를 적절한 위치에 그대로 넣어)
    4. <h2>팩트 체크: 돈의 흐름</h2>
    5. <p> (뉴스 분석 내용)</p>
    6. <h2>투자 전략: 대응 방법</h2>
    7. <p> (공격적/보수적 투자자 대응법)</p>
    8. <p style="color:grey; font-size:0.8em;">(본 콘텐츠는 투자 조언이 아닙니다.)</p>
    
    HTML 코드만 출력해. 마크다운 쓰지 마.
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{
