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
# [함수 1] 모델 선택 (Gemini 2.5 Flash 고정)
# =========================================================
MODEL_NAME = "gemini-3-flash-preview"

# =========================================================
# [함수 2] (수정됨) 뉴스 리스트 가져오기 (최대 5개)
# =========================================================
def get_science_news_list():
    print("🔍 구글 뉴스 과학 섹션 헤드라인 리스트 검색...")
    rss_url = "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            # 상위 5개 뉴스만 가져옵니다.
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
        # 최근 게시글 10개 검사 (범위를 조금 늘림)
        posts = service.posts().list(blogId=BLOG_ID, maxResults=10).execute()
        items = posts.get('items', [])
        
        for post in items:
            if news_title in post.get('content', ''):
                return True # 중복임
        return False # 새 글임
    except Exception as e:
        print(f"⚠️ 중복 확인 중 에러 (진행함): {e}")
        return False

# =========================================================
# [함수 4] 키워드 추출
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
                print("⚠️ 이미지가 부족하여 기본 이미지 사용 고려")
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
    너는 베테랑 과학 에디터야. 아래 뉴스 제목을 블로그용으로 매력적으로 다시 써줘.
    
    [원래 제목]
    {news_title}
    
    [제목 작성 규칙]
    1. **후킹(Hooking)**: 사람들의 호기심이나 궁금증을 강하게 자극하는 질문이나 문장으로 시작해. (존댓말 사용)
    2. **과학 원리**: 그 뒤에 괄호 '()'를 치고, 이 뉴스와 관련된 핵심 과학 용어나 이론을 짧게 적어.
    3. 따옴표나 불필요한 특수문자는 쓰지 마.
    
    [예시]
    - 원제: 커피가 심장병 위험 낮춘다
    -> 매일 마시는 이것, 사실 심장을 살린다? (폴리페놀 효과)
    - 원제: 제임스 웹 망원경, 가장 오래된 은하 관측
    -> 우주의 시작을 찍었다, 시간 여행의 증거일까 (빅뱅 이론)
    
    [출력]
    오직 완성된 제목 한 줄만 출력해.
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
# [함수 7] 글 작성 및 '박스 뜯기'
# =========================================================
def generate_deep_content_with_images(news, image_urls):
    print(f"🧠 AI({MODEL_NAME})가 본문 작성 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    img1 = f'<img src="{image_urls[0]}" alt="img1" style="width:100%; border-radius:10px; margin:20px 0;">' if len(image_urls)>0 else ""
    img2 = f'<img src="{image_urls[1]}" alt="img2" style="width:100%; border-radius:10px; margin:20px 0;">' if len(image_urls)>1 else ""

    prompt = f"""
당신은 과학 유튜버처럼 쉽고 재미있게 설명하는 블로거입니다.

[뉴스]
제목: {news.title}
링크: {news.link}

[글 작성 가이드]
1. **도입부**: "여러분, 이거 아셨어요?" 같은 친근한 질문으로 시작
2. **핵심 설명**: 중학생도 이해할 수 있게 비유와 예시 활용
3. **과학 원리**: 어려운 용어는 괄호로 쉽게 풀어서 설명
4. **일상 연결**: "우리 생활에서는..." 식으로 실생활 적용 사례 제시
5. **마무리**: "앞으로 어떻게 될까요?" 같은 전망으로 끝

[구조 (HTML)]
<h2>🔬 [흥미로운 제목]</h2>
<p>[호기심 자극하는 도입 - 2~3문장]</p>

{img1 if img1 else ""}

<h2>📚 이게 도대체 뭔데?</h2>
<p>[핵심 개념을 쉽게 설명 - 비유 활용]</p>

<h2>🧪 과학적으로 파헤쳐보면</h2>
<p>[원리 상세 설명 - 단계별로]</p>

{img2 if img2 else ""}

<h2>💡 우리 생활에서는?</h2>
<p>[실용적 응용 사례나 전망]</p>

<p><small>📰 원문: {news.title}</small></p>

[필수 규칙]
- 반말 금지, 친근한 해요체 사용
- 문단당 3~5문장 유지
- 전문 용어는 반드시 쉬운 말로 풀어쓰기
- HTML 태그만 출력 (```html 블록 사용 금지)
"""
    
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.7}}
    
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
# [메인 실행] (수정됨: 반복문 추가)
# =========================================================
def run_bot():
    try:
        # 1. Blogger 서비스 연결
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        # 2. 뉴스 리스트 가져오기 (최대 5개)
        news_list = get_science_news_list()
        if not news_list:
            print("❌ 가져온 뉴스가 없습니다.")
            return

        # 3. 뉴스 하나씩 순회하며 중복 체크
        target_news = None
        
        for news in news_list:
            print(f"🔎 기사 확인 중: {news.title}")
            if check_is_duplicate(service, news.title):
                print(f"🚫 [중복] 이미 포스팅된 기사입니다. 다음 기사로 넘어갑니다.")
                continue # 다음 뉴스로 점프
            else:
                print(f"✅ [통과] 새로운 기사입니다! 작업을 시작합니다.")
                target_news = news
                break # 작업할 뉴스를 찾았으니 루프 탈출
        
        # 4. 모든 뉴스가 중복이라면 종료
        if not target_news:
            print("😴 오늘은 모든 상위 뉴스가 이미 포스팅되었습니다. 봇을 종료합니다.")
            return

        # =====================================
        # 여기서부터는 target_news로 글 작성 시작
        # =====================================

        # 5. 키워드 및 이미지
        keywords = get_search_keywords(target_news.title)
        images = get_relevant_images_webp(keywords)
        
        # 6. 본문 작성
        content = generate_deep_content_with_images(target_news, images)
        if not content: 
            print("❌ 글 작성 실패")
            return

        # 7. 제목 생성 및 업로드
        final_title = generate_viral_title(target_news.title)
        
        print("📤 블로그 업로드 중...")
        body = {"kind": "blogger#post", "title": final_title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"🎉 포스팅 완료! 제목: {final_title}")
        
    except Exception as e:
        print(f"⛔ 치명적 오류: {e}")
        exit(1)

if __name__ == "__main__":
    run_bot()



