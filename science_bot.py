import os
import json
import time
import requests
import feedparser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# =========================================================
# [설정 구역] GitHub Secrets에서 환경변수 가져오기
# =========================================================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BLOG_ID = os.environ.get('BLOG_ID')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY') # 새로 추가된 키

try:
    client_env = os.environ.get('CLIENT_JSON')
    token_env = os.environ.get('TOKEN_JSON')
    
    if not client_env or not token_env or not PEXELS_API_KEY:
        raise ValueError("GitHub Secrets에 필수 값(CLIENT, TOKEN, PEXELS_API_KEY)이 없습니다.")
        
    CLIENT_JSON = json.loads(client_env)
    TOKEN_JSON = json.loads(token_env)
except Exception as e:
    print("⛔ JSON 파싱 실패 또는 Pexels 키 누락. Secrets 값을 확인하세요.")
    print(f"에러 상세: {e}")
    exit(1)

# =========================================================
# [함수 1] Gemini 2.5 Flash  선택
# =========================================================

MODEL_NAME = "gemini-2.5-flash"

# =========================================================
# [함수 2] (개선됨) 구글 뉴스 과학 섹션 헤드라인 가져오기
# =========================================================
def get_top_science_news():
    print("🔍 구글 뉴스 과학 섹션의 탑 헤드라인을 검색합니다...")
    # 변경점: 단순 검색이 아닌 '과학 토픽'의 헤드라인 RSS 사용 (인기/중요도 반영)
    rss_url = "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(rss_url)
    
    if feed.entries:
        # 가장 상단에 있는 뉴스가 현재 가장 화제인 뉴스
        news = feed.entries[0]
        print(f"✅ 선정된 탑 뉴스: {news.title}")
        return news
    else:
        return None

# =========================================================
# [신규 함수 3] 이미지 검색을 위한 영어 키워드 추출
# =========================================================
def get_search_keywords(news_title):
    print("🧠 이미지 검색용 키워드를 추출합니다...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"다음 뉴스 제목에서 이미지 검색에 사용할 수 있는 핵심 영어 명사 키워드 2~3개를 추출해서 콤마로 구분해줘. 다른 말은 하지 마. 뉴스 제목: {news_title}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    headers = {'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            keywords = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            print(f"🔑 추출된 키워드: {keywords}")
            return keywords
        return "science, technology" # 실패 시 기본 키워드
    except:
        return "science, technology"

# =========================================================
# [신규 함수 4] Pexels에서 관련 WebP 이미지 2장 가져오기
# =========================================================
def get_relevant_images_webp(query):
    print(f"🖼️ Pexels에서 이미지 검색 중... Query: {query}")
    url = "https://api.pexels.com/v1/search"
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": query,
        "per_page": 2,     # 2장만 요청
        "orientation": "landscape", # 가로 사진 선호
        "size": "medium"   # 적당한 크기
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            image_urls = []
            for photo in data.get('photos', []):
                # 원본 URL에 파라미터를 붙여 WebP 형식으로 변환
                base_url = photo['src']['original']
                webp_url = f"{base_url}?auto=compress&fm=webp&w=800"
                image_urls.append(webp_url)
            
            if len(image_urls) >= 2:
                 print("✅ 이미지 2장 확보 완료 (WebP)")
                 return image_urls
            else:
                 print("⚠️ 관련 이미지를 충분히 찾지 못했습니다.")
                 return []
        else:
            print(f"⛔ Pexels API 오류: {response.status_code}")
            return []
    except Exception as e:
        print(f"⛔ 이미지 검색 중 오류: {e}")
        return []

# =========================================================
# [함수 5] (개선됨) CoT 및 이미지 삽입 글 작성
# =========================================================
def generate_deep_content_with_images(news, image_urls):
    print(f"🧠 AI({MODEL_NAME})가 이미지 배치를 포함한 글 작성을 시작합니다...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # 이미지 태그 준비 (이미지가 있을 경우에만)
    img_tag1 = f'<img src="{image_urls[0]}" alt="기사 관련 이미지 1" style="width:100%; height:auto; margin: 20px 0; border-radius: 8px;">' if len(image_urls) > 0 else ""
    img_tag2 = f'<img src="{image_urls[1]}" alt="기사 관련 이미지 2" style="width:100%; height:auto; margin: 20px 0; border-radius: 8px;">' if len(image_urls) > 1 else ""

    prompt = f"""
    당신은 과학 전문 칼럼니스트입니다. 아래 뉴스에 대해 깊이 있는 해설 글을 HTML로 작성하세요.

    [뉴스 정보]
    제목: {news.title}
    링크: {news.link}

    [지시사항]
    1. **Chain of Thought**: 먼저 뉴스 속 핵심 과학 원리를 파악하고, 기초 지식을 백과사전처럼 자세히 설명한 뒤, 뉴스 내용과 연결하세요.
    2. **팩트 체크**: 과학적 오류가 없도록 주의하세요.
    3. **이미지 배치**: 아래 제공된 2개의 이미지 태그를 글의 문맥에 맞는 적절한 위치(문단 사이)에 자연스럽게 삽입하세요. (반드시 2개 모두 사용할 것)
       - 이미지 태그 1: {img_tag1}
       - 이미지 태그 2: {img_tag2}

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
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3}
    }
    headers = {'Content-Type': 'application/json'}
    
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if 'candidates' in data:
                    return data['candidates'][0]['content']['parts'][0]['text']
                else: return None
            elif response.status_code == 429:
                print(f"⏳ 사용량 제한! 30초 대기... ({attempt+1}/3)")
                time.sleep(30)
            else:
                print(f"⛔ 에러: {response.text}")
                return None
        except Exception as e:
            print(f"⛔ 통신 에러: {e}")
            time.sleep(5)
    return None

# =========================================================
# [메인 실행 함수]
# =========================================================
def run_bot():
    try:
        # 1. 가장 화제인 뉴스 가져오기
        news = get_top_science_news()
        if not news:
            print("❌ 뉴스를 찾을 수 없습니다.")
            return

        # 2. 이미지 검색을 위한 키워드 추출
        keywords = get_search_keywords(news.title)
        
        # 3. Pexels에서 WebP 이미지 가져오기
        image_urls = get_relevant_images_webp(keywords)

        # 4. 이미지 포함하여 글 작성 요청
        content = generate_deep_content_with_images(news, image_urls)
        if not content:
            print("❌ 글 작성 실패.")
            return

        # 5. 블로그 업로드
        print("📤 블로그 업로드 준비 중...")
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)
        
        blog_title = f"[과학칼럼] {news.title}"
        body = {"kind": "blogger#post", "title": blog_title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print("🎉 포스팅 완료! (화제 뉴스 + 심층 분석 + WebP 이미지 2장)")
        
    except Exception as e:
        print(f"⛔ 치명적 오류 발생: {e}")
        exit(1)

if __name__ == "__main__":
    run_bot()
