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
BLOG_ID = os.environ.get('BLOG_ID')
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

# =========================================================
# [함수 1] 모델 선택
# =========================================================
MODEL_NAME = "gemini-2.5-flash"

# =========================================================
# [함수 2] 테크 뉴스 리스트 가져오기 (RSS URL 변경됨)
# =========================================================
def get_tech_news_list():
    print("🔍 구글 뉴스 [테크/IT] 섹션 헤드라인 검색...")
    # ★ 여기가 핵심 변경 포인트: SCIENCE -> TECHNOLOGY
    rss_url = "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            top_5_news = feed.entries[:5]
            print(f"✅ 총 {len(top_5_news)}개의 최신 테크 뉴스를 가져왔습니다.")
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
# [함수 4] 키워드 추출 (테크 용어 위주)
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"뉴스 제목: '{news_title}'. 이 뉴스의 핵심 '영어' 테크 키워드 3개를 콤마로 구분해줘. (예: AI, Smartphone, Semiconductor)"
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "technology, innovation"

# =========================================================
# [함수 5] 이미지 검색
# =========================================================
def get_relevant_images_webp(query):
    print(f"🖼️ Pexels 이미지 검색: {query}")
    try:
        resp = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": PEXELS_API_KEY}, params={"query": query, "per_page": 2, "orientation": "landscape", "size": "medium"})
        if resp.status_code == 200:
            urls = [p['src']['original'] + "?auto=compress&fm=webp&w=800" for p in resp.json().get('photos', [])]
            if len(urls) >= 2:
                print(f"✅ 이미지 {len(urls)}장 확보")
                return urls
            else:
                return []
    except Exception as e:
        print(f"⛔ 이미지 검색 에러: {e}")
    return []

# =========================================================
# [함수 6] 후킹 제목 생성 (테크 에디터 버전)
# =========================================================
def generate_viral_title(news_title):
    print("🎣 AI가 클릭을 유도하는 테크 제목을 짓고 있습니다...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    너는 인기 IT/테크 블로그의 메인 에디터야. 
    아래 뉴스 제목을 사람들이 무조건 클릭하게 만드는 매력적인 제목으로 바꿔줘.
    
    [원래 제목]
    {news_title}
    
    [제목 작성 규칙]
    1. **트렌디함**: 최신 기술 트렌드를 반영하여 호기심을 자극해. (존댓말 사용)
    2. **핵심 요약**: 괄호 '()' 안에 핵심 기술명이나 기업명, 또는 효과를 적어.
    3. 따옴표 제외.
    
    [예시]
    - 원제: 애플, 새로운 아이폰 공개
    -> 아이폰 16, 무엇이 달라졌을까? 혁신 포인트 총정리 (애플 이벤트)
    - 원제: 엔비디아 주가 폭등, AI 칩 수요 증가
    -> AI 시대의 심장, 엔비디아가 세상을 바꾸는 법 (GPU 혁명)
    
    [출력]
    완성된 제목 한 줄만 출력해.
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
# [함수 7] 글 작성 (테크 리뷰어 페르소나)
# =========================================================
def generate_deep_content_with_images(news, image_urls):
    print(f"🧠 AI({MODEL_NAME})가 테크 리뷰를 작성 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    img1 = f'<img src="{image_urls[0]}" alt="Tech Image 1" style="width:100%; border-radius:10px; margin:20px 0;">' if len(image_urls)>0 else ""
    img2 = f'<img src="{image_urls[1]}" alt="Tech Image 2" style="width:100%; border-radius:10px; margin:20px 0;">' if len(image_urls)>1 else ""

    prompt = f"""
    당신은 통찰력 있는 'IT/테크 전문 칼럼니스트'입니다. 
    아래 테크 뉴스에 대해 블로그 독자들이 이해하기 쉬운 해설 글을 HTML로 작성하세요.

    [뉴스 정보]
    제목: {news.title}
    링크: {news.link}
    
    [글의 구성 (HTML)]
    - <p>도입부 (독자의 궁금증 유발, 최신 트렌드 언급)</p>
    - {img1}
    - <h2>핵심 기술 및 혁신 포인트</h2>
    - <p>이 뉴스가 왜 중요한지, 어떤 기술이 적용되었는지 상세 설명 (전문 용어는 쉽게 풀이)</p>
    - {img2}
    - <h2>시장 전망 및 우리의 삶에 미칠 영향</h2>
    - <p>앞으로의 변화 예측, 소비자에게 주는 혜택 등</p>
    - <p><small>출처: {news.title}</small></p>
    
    [필수 형식]
    - HTML 태그만 출력 (h2, p, ul, li 등).
    - ```html 마크다운 절대 금지.
    - 말투는 전문적이지만 친절한 '해요체'.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3}}
    
    for _ in range(3):
        try:
            res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
            if res.status_code == 200:
                content = res.json()['candidates'][0]['content']['parts'][0]['text']
                return content.replace("```html", "").replace("```", "").strip()
            elif res.status_code == 429:
                time.sleep(30)
        except:
            time.sleep(5)
    return None

# =========================================================
# [메인 실행]
# =========================================================
def run_bot():
    try:
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        # 1. 테크 뉴스 리스트 가져오기
        news_list = get_tech_news_list()
        if not news_list:
            print("❌ 가져온 뉴스가 없습니다.")
            return

        target_news = None
        for news in news_list:
            print(f"🔎 기사 확인 중: {news.title}")
            if check_is_duplicate(service, news.title):
                print(f"🚫 [중복] 패스합니다.")
                continue
            else:
                print(f"✅ [선택] 작업을 시작합니다.")
                target_news = news
                break
        
        if not target_news:
            print("😴 오늘은 새로운 테크 뉴스가 없습니다.")
            return

        keywords = get_search_keywords(target_news.title)
        images = get_relevant_images_webp(keywords)
        
        content = generate_deep_content_with_images(target_news, images)
        if not content: return

        final_title = generate_viral_title(target_news.title)
        
        print("📤 테크 블로그 업로드 중...")
        body = {"kind": "blogger#post", "title": final_title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"🎉 포스팅 완료! 제목: {final_title}")
        
    except Exception as e:
        print(f"⛔ 치명적 오류: {e}")
        exit(1)

if __name__ == "__main__":
    run_bot()
