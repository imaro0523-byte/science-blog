import os
import json
import time
import requests
import feedparser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# =========================================================
# [설정 구역] 환경변수 및 보안 설정
# =========================================================
print("🔧 환경변수 점검 중...")

# 1. API 키 확인
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')

# 2. 블로그 ID 확인 (이름이 다를 경우를 대비해 2가지 다 체크)
BLOG_ID = os.environ.get('MONEY_BLOG_ID')

# 3. 필수값 검증 (시작 전에 미리 체크해서 시간 낭비 방지)
if not GEMINI_API_KEY:
    print("❌ [오류] GEMINI_API_KEY가 없습니다.")
    exit(1)
if not BLOG_ID:
    print("❌ [오류] BLOG_ID(또는 MONEY_BLOG_ID)가 설정되지 않았습니다. GitHub Secrets를 확인하세요.")
    exit(1)
if not PEXELS_API_KEY:
    print("⚠️ [주의] PEXELS_API_KEY가 없습니다. 이미지가 없이 글만 작성됩니다.")

print(f"✅ 블로그 ID 확인됨: {BLOG_ID[:3]}*****")

# 4. 구글 인증 토큰 로딩
try:
    client_env = os.environ.get('CLIENT_JSON')
    token_env = os.environ.get('TOKEN_JSON')
    
    CLIENT_JSON = json.loads(client_env) if client_env else {}
    TOKEN_JSON = json.loads(token_env) if token_env else {}
except Exception as e:
    print(f"⛔ 설정 로딩 에러: {e}")

MODEL_NAME = "gemini-3-flash-preview"

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
        print(f"⚠️ 중복 확인 패스 (이유: {e})")
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
# [함수 5] 이미지 검색
# =========================================================
def get_relevant_images_webp(query):
    if not PEXELS_API_KEY:
        return []
        
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
# [함수 6] 본문 작성 (치환 방식)
# =========================================================
def generate_content_safe(news, image_urls, dashboard_html):
    print(f"🧠 AI가 글을 작성합니다...")
    
    img_tag = ""
    if image_urls:
        img_tag = f'<img src="{image_urls[0]}" alt="Money Image" style="width:100%; border-radius:10px; margin:20px 0;">'
    
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
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3}}
    
    for i in range(3):
        try:
            res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
            if res.status_code == 200:
                raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                clean_text = raw_text.replace("```html", "").replace("```", "").strip()
                
                # ★ 대시보드 교체
                final_content = clean_text.replace("[[DASHBOARD]]", dashboard_html)
                return final_content
            else:
                print("⏳ AI 응답 대기 중...")
                time.sleep(5)
        except Exception as e:
            print(f"⚠️ 작성 중 에러: {e}")
            time.sleep(5)
            
    return None

# =========================================================
# [함수 7] 제목 생성
# =========================================================
def generate_viral_title(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"뉴스 제목: '{news_title}'. 유튜브 썸네일 스타일의 자극적인 제목 1개만 뽑아줘. (괄호 사용, 질문형 등)"
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().replace('"', '')
    except:
        return news_title

# =========================================================
# [메인 실행]
# =========================================================
def run_bot():
    print("▶️ 머니 봇 시작")
    try:
        # 인증 객체 생성
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        # 1. 뉴스 확보
        news_list = get_tech_news_list()
        if not news_list:
            print("❌ 뉴스 리스트가 비어있습니다. 종료.")
            return

        target_news = None
        for news in news_list:
            print(f"🔎 체크: {news.title}")
            if check_is_duplicate(service, news.title):
                print("   ↪️ 중복. 패스.")
            else:
                target_news = news
                print("   ✅ 선택됨!")
                break
        
        if not target_news:
            print("😴 작성할 새로운 뉴스가 없습니다. 종료.")
            return

        # 2. 리소스 준비
        keywords = get_search_keywords(target_news.title)
        images = get_relevant_images_webp(keywords)
        dashboard = get_dashboard_html() 

        # 3. 글 작성
        content = generate_content_safe(target_news, images, dashboard)
        if not content:
            print("❌ 본문 생성 실패. 종료.")
            return

        # 4. 제목 및 업로드 (★ 여기서 BLOG_ID가 꼭 필요함)
        title = generate_viral_title(target_news.title)
        print(f"📤 업로드 진행: {title}")
        print(f"   (타겟 블로그 ID: {BLOG_ID})")
        
        body = {"kind": "blogger#post", "title": title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print("🎉 포스팅 성공!")

    except Exception as e:
        print(f"⛔ 치명적 오류 발생: {e}")
        exit(1)

if __name__ == "__main__":
    run_bot()
