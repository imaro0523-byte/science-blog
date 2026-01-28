import os
import json
import requests
import feedparser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# GitHub Secrets에서 정보 가져오기
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BLOG_ID = os.environ.get('BLOG_ID')

# JSON 파싱 시 에러 방지를 위한 예외 처리
try:
    CLIENT_JSON = json.loads(os.environ.get('CLIENT_JSON'))
    TOKEN_JSON = json.loads(os.environ.get('TOKEN_JSON'))
except Exception as e:
    print("⛔ Secrets JSON 로딩 실패! 형식(따옴표 등)을 확인하세요.")
    print(f"에러 상세: {e}")
    exit(1)

MODEL_NAME = "gemini-2.5-flash" 

def get_latest_news():
    print("🔍 뉴스 검색 중...")
    rss_url = "https://news.google.com/rss/search?q=science+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(rss_url)
    return feed.entries[0] if feed.entries else None

def generate_content(news):
    print(f"🤖 AI({MODEL_NAME})에게 요청 보냄...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"당신은 과학 블로거입니다. 다음 뉴스를 HTML로 요약하세요: {news.title}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    # ★ 수정됨: 헤더 추가 및 에러 확인 로직 강화
    headers = {'Content-Type': 'application/json'}
    response = requests.post(url, json=payload, headers=headers)
    
    # 상태 코드가 200(성공)이 아니면 에러 메시지 출력하고 종료
    if response.status_code != 200:
        print(f"⛔ API 호출 실패! 상태 코드: {response.status_code}")
        print(f"▼ 구글 서버 응답 내용:\n{response.text}")
        raise Exception("Gemini API Error")
        
    response_json = response.json()
    
    # 안전장치: candidates 키가 없는 경우
    if 'candidates' not in response_json:
        print("⛔ 응답에 'candidates'가 없습니다. (필터링되었거나 오류)")
        print(f"▼ 전체 응답:\n{response_json}")
        raise Exception("No Content Generated")

    return response_json['candidates'][0]['content']['parts'][0]['text']

def run_bot():
    news = get_latest_news()
    if news:
        print(f"✅ 뉴스 선정: {news.title}")
        try:
            # TOKEN_JSON 데이터를 사용해 인증
            creds = Credentials.from_authorized_user_info(TOKEN_JSON)
            service = build('blogger', 'v3', credentials=creds)
            
            content = generate_content(news)
            
            body = {"kind": "blogger#post", "title": f"[과학뉴스] {news.title}", "content": content}
            service.posts().insert(blogId=BLOG_ID, body=body).execute()
            print("🎉 GitHub Actions 포스팅 성공!")
            
        except Exception as e:
            print(f"⛔ 실행 중 치명적 오류 발생: {e}")
            # GitHub Actions에서 빨간 X를 띄우기 위해 강제 종료
            exit(1)
    else:
        print("❌ 검색된 뉴스가 없습니다.")

if __name__ == "__main__":
    run_bot()

