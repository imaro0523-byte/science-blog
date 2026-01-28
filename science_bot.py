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

try:
    # JSON 문자열을 파이썬 객체로 변환 (따옴표 에러 방지용 안전 장치)
    client_env = os.environ.get('CLIENT_JSON')
    token_env = os.environ.get('TOKEN_JSON')
    
    if not client_env or not token_env:
        raise ValueError("GitHub Secrets에 JSON 값이 없습니다.")
        
    CLIENT_JSON = json.loads(client_env)
    TOKEN_JSON = json.loads(token_env)
except Exception as e:
    print("⛔ JSON 파싱 또는 로딩 실패. Secrets 값을 확인하세요.")
    print(f"에러 상세: {e}")
    exit(1)

# =========================================================
# [핵심 함수 1] 사용 가능한 최신 Gemini 모델 내가 고정함
# =========================================================

MODEL_NAME = "gemini-2.5-flash"

# =========================================================
# [핵심 함수 2] 뉴스 가져오기
# =========================================================
def get_latest_news():
    print("🔍 최신 과학 뉴스 검색 중...")
    # RSS 피드: 구글 뉴스 과학 섹션 (한국어)
    rss_url = "https://news.google.com/rss/search?q=science+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(rss_url)
    
    if feed.entries:
        news = feed.entries[0]
        print(f"✅ 뉴스 선정: {news.title}")
        return news
    else:
        return None

# =========================================================
# [핵심 함수 3] Chain of Thought(CoT) 프롬프트로 글 작성
# =========================================================
def generate_deep_content(news):
    print(f"🧠 AI({MODEL_NAME})가 깊이 있는 사고(Reasoning)를 시작합니다...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # ★ 여기가 마법의 프롬프트 구역입니다 ★
    prompt = f"""
    당신은 20년 경력의 과학 전문 칼럼니스트이자 팩트체커입니다.
    아래 뉴스 제목을 바탕으로, 일반인을 위한 깊이 있고 정확한 과학 해설 블로그 글을 작성하세요.

    [뉴스 정보]
    제목: {news.title}
    링크: {news.link}

    [작성 절차 (Chain of Thought)]
    글을 쓰기 전에 다음 단계를 머릿속으로 먼저 수행하세요:
    1. **키워드 분석**: 뉴스 제목에서 핵심 과학 개념(예: 양자 얽힘, 효소 작용, 블랙홀 등)을 추출하십시오.
    2. **배경 지식 확장**: 해당 개념의 교과서적인 정의, 원리, 발견 역사를 떠올리십시오.
    3. **연결**: 이 기초 과학 원리가 뉴스 속 최신 발견과 어떻게 연결되는지 논리적으로 구성하십시오.
    4. **팩트 체크**: 작성된 내용에 비과학적 비약이나 오류가 없는지 스스로 검증하십시오.

    [글의 구성 (HTML 형식)]
    반드시 HTML 태그(<h2>, <p>, <b>, <ul>, <li>, <br>)만 사용하여 출력하세요. 마크다운(```)은 쓰지 마세요.
    
    - **제목 (h2)**: 뉴스 제목을 흥미롭게 각색
    - **도입부 (p)**: 뉴스의 핵심 내용을 요약 (50자 이내)
    - **기초 과학 돋보기 (h2 + p)**: 이 뉴스를 이해하기 위해 꼭 알아야 할 과학 원리 설명 (교양 수준)
    - **심층 분석 (h2 + p)**: 원리를 바탕으로 한 뉴스의 상세 해설
    - **미래 전망 및 결론 (p)**: 이 발견이 가져올 과학적 의의
    - **출처 (p)**: <small>원문 뉴스: {news.title}</small>

    [주의사항]
    - 말투는 친절하고 명확한 '해요체'를 사용하세요.
    - 과학적 사실이 불확실한 경우 단정 짓지 말고 "추정됩니다" 또는 "연구 중입니다"라고 표현하세요.
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        # 온도(Temperature)를 낮춰서 팩트에 기반한 차분한 글을 쓰게 유도
        "generationConfig": {"temperature": 0.3} 
    }
    headers = {'Content-Type': 'application/json'}
    
    # 429 에러 방지용 재시도 로직
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                if 'candidates' in data:
                    return data['candidates'][0]['content']['parts'][0]['text']
                else:
                    print("⛔ 응답에 내용이 없습니다(필터링됨).")
                    return None
            elif response.status_code == 429:
                print(f"⏳ 사용량 제한! 30초 대기 중... ({attempt+1}/3)")
                time.sleep(30)
            else:
                print(f"⛔ 에러 발생 코드: {response.status_code}")
                print(response.text)
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
        news = get_latest_news()
        if not news:
            print("❌ 검색된 뉴스가 없습니다.")
            return

        content = generate_deep_content(news)
        if not content:
            print("❌ 글 작성 실패.")
            return

        print("📤 블로그 업로드 준비 중...")
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)
        
        # 블로그 제목에 [과학칼럼] 말머리 추가
        blog_title = f"[과학칼럼] {news.title}"
        body = {
            "kind": "blogger#post",
            "title": blog_title,
            "content": content
        }
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print("🎉 포스팅 완료! 과학적으로 더 완벽해졌습니다.")
        
    except Exception as e:
        print(f"⛔ 치명적 오류 발생: {e}")
        exit(1)

if __name__ == "__main__":
    run_bot()



