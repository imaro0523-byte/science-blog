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
# [함수 2] 뉴스 가져오기
# =========================================================
def get_top_science_news():
    print("🔍 구글 뉴스 과학 섹션 헤드라인 검색...")
    rss_url = "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            print(f"✅ 선정된 뉴스: {feed.entries[0].title}")
            return feed.entries[0]
    except Exception as e:
        print(f"⛔ 뉴스 검색 에러: {e}")
    return None

# =========================================================
# [함수 3] 키워드 추출
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"뉴스 제목: '{news_title}'. 이 뉴스의 핵심 영어 명사 키워드 3개를 콤마로 구분해줘."
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "science, technology"

# =========================================================
# [함수 4] 이미지 검색
# =========================================================
def get_relevant_images_webp(query):
    print(f"🖼️ Pexels 이미지 검색: {query}")
    try:
        resp = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": PEXELS_API_KEY}, params={"query": query, "per_page": 2, "orientation": "landscape", "size": "medium"})
        if resp.status_code == 200:
            urls = [p['src']['original'] + "?auto=compress&fm=webp&w=800" for p in resp.json().get('photos', [])]
            print(f"✅ 이미지 {len(urls)}장 확보")
            return urls
    except Exception as e:
        print(f"⛔ 이미지 검색 에러: {e}")
    return []

# =========================================================
# [함수 5] ★수정됨★ 글 작성 및 '박스 뜯기'
# =========================================================
def generate_deep_content_with_images(news, image_urls):
    print(f"🧠 AI({MODEL_NAME})가 글 작성 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    img1 = f'<img src="{image_urls[0]}" alt="img1" style="width:100%; border-radius:10px; margin:20px 0;">' if len(image_urls)>0 else ""
    img2 = f'<img src="{image_urls[1]}" alt="img2" style="width:100%; border-radius:10px; margin:20px 0;">' if len(image_urls)>1 else ""

    prompt = f"""
    당신은 과학 전문 칼럼니스트입니다. 아래 뉴스에 대해 깊이 있는 해설 글을 HTML로 작성하세요.

    [뉴스 정보]
    제목: {news.title}
    링크: {news.link}
    
    [작성 절차 (Chain of Thought)]
    글을 쓰기 전에 다음 단계를 머릿속으로 먼저 수행하세요:
    1. **키워드 분석**: 뉴스 제목에서 핵심 과학 개념(예: 양자 얽힘, 효소 작용, 블랙홀 등)을 추출하십시오.
    2. **배경 지식 확장**: 해당 개념의 교과서적인 정의, 원리, 발견 역사를 떠올리십시오.
    3. **연결**: 이 기초 과학 원리가 뉴스 속 최신 발견과 어떻게 연결되는지 논리적으로 구성하십시오.
    4. **팩트 체크**: 작성된 내용에 비과학적 비약이나 오류가 없는지 스스로 검증하십시오.
    5. **이미지 배치**: 아래 제공된 2개의 이미지 태그를 글의 문맥에 맞는 적절한 위치(문단 사이)에 자연스럽게 삽입하세요. (반드시 2개 모두 사용할 것)
       - 이미지 태그 1: {img1}
       - 이미지 태그 2: {img2}

    [글의 구성 (HTML)]
    - <h2>제목 (흥미롭게 각색)</h2>
    - <p>도입부 요약</p>
    - (적절한 위치에 이미지 태그 삽입)
    - <h2>기초 과학 원리 해설</h2>
    - <p>원리 상세 설명</p>
    - (적절한 위치에 이미지 태그 삽입)
    - <h2>뉴스 심층 분석</h2>
    - <p>분석 내용</p>
    - <p>결론 및 의의</p>
    - <p><small>원문 뉴스: {news.title}</small></p>
    
    [필수 형식]
    HTML 태그(<h2>, <p>, <ul>, <li> 등)만 출력하세요. 
    마크다운 코드 블록(```html)은 절대 사용하지 마세요.

    [주의사항]
    - 말투는 친절하고 명확한 '해요체'를 사용하세요.
    - 과학적 사실이 불확실한 경우 단정 짓지 말고 "추정됩니다" 또는 "연구 중입니다"라고 표현하세요.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3}}
    
    for _ in range(3):
        try:
            res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
            if res.status_code == 200:
                data = res.json()
                if 'candidates' in data:
                    content = data['candidates'][0]['content']['parts'][0]['text']
                    
                    # ★★★ 여기가 핵심 수정 부분입니다! ★★★
                    # AI가 씌운 마크다운 박스(```html ... ```)를 강제로 벗겨냅니다.
                    content = content.replace("```html", "").replace("```", "").strip()
                    
                    return content
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
        news = get_top_science_news()
        if not news: return
        
        keywords = get_search_keywords(news.title)
        images = get_relevant_images_webp(keywords)
        content = generate_deep_content_with_images(news, images)
        
        if not content:
            print("❌ 글 작성 실패")
            return

        print("📤 블로그 업로드 중...")
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)
        
        body = {"kind": "blogger#post", "title": f"[과학칼럼] {news.title}", "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print("🎉 포스팅 성공!")
        
    except Exception as e:
        print(f"⛔ 치명적 오류: {e}")
        exit(1)

if __name__ == "__main__":
    run_bot()

