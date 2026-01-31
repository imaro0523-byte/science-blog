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

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')

# 블로그 ID 확인 (안전장치: 여러 이름으로 시도)
BLOG_ID = os.environ.get('MONEY_BLOG_ID')

# 필수값 검증
if not GEMINI_API_KEY:
    print("❌ [오류] GEMINI_API_KEY가 없습니다.")
    exit(1)
if not BLOG_ID:
    print("❌ [오류] BLOG_ID(또는 MONEY_BLOG_ID)가 설정되지 않았습니다. GitHub Secrets를 확인하세요.")
    exit(1)

print(f"✅ 타겟 블로그 ID: {BLOG_ID[:5]}*****")

# 구글 인증 토큰 로딩
try:
    client_env = os.environ.get('CLIENT_JSON')
    token_env = os.environ.get('TOKEN_JSON')
    
    CLIENT_JSON = json.loads(client_env) if client_env else {}
    TOKEN_JSON = json.loads(token_env) if token_env else {}
except Exception as e:
    print(f"⛔ 설정 로딩 에러: {e}")

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
    btc_color = "#d63031" if btc_chg >= 0 else "#0984e3" # 빨강/파랑
    btc_arrow = "▲" if btc_chg >= 0 else "▼"
    
    fng_emoji = "😐"
    if fng >= 75: fng_emoji = "🔥 탐욕"
    elif fng <= 25: fng_emoji = "🥶 공포"

    html = f"""
    <div style="background: #ffffff; border: 1px solid #e0e0e0; border-left: 5px solid #2d3436; border-radius: 8px; padding: 20px; margin-bottom: 30px; font-family: sans-serif; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
        <h3 style="text-align:center; margin:0 0 15px 0; color:#2d3436; font-size: 18px;">📊 Today's Market Pulse</h3>
        <div style="display:flex; justify-content:space-around; text-align:center; border-top: 1px dashed #e0e0e0; padding-top: 15px;">
            <div>
                <div style="font-size:13px; color:#636e72; margin-bottom: 5px;">Bitcoin (KRW)</div>
                <div style="color:{btc_color}; font-weight:bold; font-size:18px;">{btc_arrow} {btc:,.0f}원</div>
                <div style="font-size:12px; color:{btc_color};">({btc_chg:.2f}%)</div>
            </div>
            <div style="border-left: 1px solid #eee;"></div>
            <div>
                <div style="font-size:13px; color:#636e72; margin-bottom: 5px;">Fear & Greed</div>
                <div style="font-weight:bold; font-size:18px; color:#2d3436;">{fng} <span style="font-size:16px;">{fng_emoji}</span></div>
                <div style="font-size:12px; color:#636e72;">Index Score</div>
            </div>
        </div>
    </div>
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
    # [수정됨] URL에서 불필요한 마크다운 기호 제거
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"뉴스 제목: '{news_title}'. 핵심 영어 키워드 3개만 콤마로 구분해. (예: Bitcoin, Economy, Inflation)"
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
# [함수 6] 본문 작성 (인사이트 중심 프롬프트로 변경)
# =========================================================
def generate_content_safe(news, image_urls, dashboard_html):
    print(f"🧠 AI가 심층 분석(Insight) 글을 작성합니다...")
    
    img_tag = ""
    if image_urls:
        img_tag = f'<img src="{image_urls[0]}" alt="Insight Image" style="width:100%; border-radius:8px; margin:25px 0; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">'
    
    prompt = f"""
    당신은 20년 경력의 '글로벌 경제 수석 애널리스트'입니다.
    아래 뉴스를 단순히 요약하지 말고, 이면의 배경과 앞으로 미칠 파급력을 심층 분석해 주세요.
    마치 추가 조사를 수행한 것처럼 깊이 있는 정보를 제공해야 합니다.

    [뉴스 정보]
    - 제목: {news.title}
    - 링크: {news.link}
    
    [작성 가이드라인]
    1. '사라/마라' 식의 직접적인 투자 조언은 지양합니다.
    2. 대신, 독자가 현상을 꿰뚫어 볼 수 있는 '통찰력(Insight)'을 제공하세요.
    3. 전문적인 용어는 쉽게 풀어서 설명하세요.
    4. 문체는 정중하고 지적인 '해요체'를 사용하세요. (예: "분석됩니다.", "주목할 필요가 있습니다.")
    
    [글 구조 (HTML 포맷)]
    1. 맨 첫 줄에 정확히 [[DASHBOARD]] 라고만 적으세요.
    2. <h3>프롤로그</h3>: 뉴스의 핵심을 요약하고, 왜 이 이슈가 지금 중요한지 화두를 던지세요.
    3. {img_tag} (이 코드를 적절한 위치에 그대로 삽입)
    4. <h3>심층 분석: 뉴스의 이면</h3>: 이 뉴스가 발생한 배경, 과거 사례와의 비교, 혹은 숨겨진 상관관계를 설명하세요. (당신의 지식을 총동원하세요)
    5. <h3>향후 전망 및 인사이트</h3>: 이 사건이 시장(주식/코인/경제)에 미칠 장기적인 영향과 시나리오를 제시하세요.
    6. <hr>
    7. <p style="color:#7f8c8d; font-size:0.85em; text-align:center;">(본 콘텐츠는 AI 기반의 분석 자료이며, 투자의 책임은 전적으로 본인에게 있습니다.)</p>
    
    HTML 태그(h3, p, hr 등)만 출력하세요. 마크다운(```)은 사용 금지.
    """
    
    # [수정됨] URL에서 불필요한 마크다운 기호 제거
    url = f"[https://generativelanguage.googleapis.com/v1beta/models/](https://generativelanguage.googleapis.com/v1beta/models/){MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.4}} 
    
    for i in range(3):
        try:
            res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
            if res.status_code == 200:
                raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                clean_text = raw_text.replace("```html", "").replace("```", "").strip()
                
                # 대시보드 교체
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
# [함수 7] 제목 생성 (** 제거 기능 추가)
# =========================================================
def generate_viral_title(news_title):
    # [수정됨] URL에서 불필요한 마크다운 기호 제거
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    뉴스 제목: '{news_title}'
    
    이 뉴스를 다룬 블로그 포스팅의 제목을 지어주세요.
    단순한 속보 전달보다는, '분석'과 '인사이트'가 담겨 있다는 느낌을 주는 매력적인 제목이어야 합니다.
    
    [예시]
    - 엔비디아 급등 -> 엔비디아 급등, AI 버블일까 새로운 챕터일까? (심층 분석)
    - 금리 동결 -> 금리 동결의 진짜 의미, 시장은 이미 답을 알고 있다
    
    [제약]
    따옴표나 ** 같은 특수문자는 절대 쓰지 마세요. 제목 한 줄만 출력하세요.
    """
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        title = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # 제목 정제
        clean_title = title.replace('"', '').replace("'", "").replace("**", "").replace("__", "")
        return clean_title
    except:
        return news_title

# =========================================================
# [메인 실행]
# =========================================================
def run_bot():
    print("▶️ 머니 인사이트 봇 시작")
    try:
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

        # 4. 제목 및 업로드
        title = generate_viral_title(target_news.title)
        print(f"📤 업로드 진행: {title}")
        
        body = {"kind": "blogger#post", "title": title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print("🎉 포스팅 성공!")

    except Exception as e:
        print(f"⛔ 치명적 오류 발생: {e}")
        exit(1)

if __name__ == "__main__":
    run_bot()
