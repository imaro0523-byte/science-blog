import os
import json
import requests
import feedparser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# 환경 변수 가져오기
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BLOG_ID = os.environ.get('BLOG_ID')
TOKEN_JSON_STR = os.environ.get('TOKEN_JSON')

MODEL_NAME = "gemini-2.5-flash"

def get_latest_news():
    rss_url = "https://news.google.com/rss/search?q=science+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(rss_url)
    return feed.entries[0] if feed.entries else None

def generate_content(news):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"당신은 과학 전문 블로거입니다. 다음 뉴스를 바탕으로 블로그 글을 HTML 형식으로 작성하세요. 제목: {news.title}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    response = requests.post(url, json=payload)
    result = response.json()
    
    # 에러 디버깅을 위한 출력
    if 'candidates' not in result:
        print(f"❌ AI 응답 에러: {json.dumps(result, indent=2, ensure_ascii=False)}")
        return None
        
    return result['candidates'][0]['content']['parts'][0]['text']

def run_bot():
    if not TOKEN_JSON_STR:
        print("❌ 에러: TOKEN_JSON이 설정되지 않았습니다.")
        return

    news = get_latest_news()
    if news:
        print(f"✅ 뉴스 선정: {news.title}")
        
        # TOKEN_JSON 문자열을 딕셔너리로 변환하여 인증
        token_info = json.loads(TOKEN_JSON_STR)
        creds = Credentials.from_authorized_user_info(token_info)
        service = build('blogger', 'v3', credentials=creds)
        
        content = generate_content(news)
        if content:
            body = {
                "kind": "blogger#post",
                "title": f"[과학뉴스] {news.title}",
                "content": content
            }
            service.posts().insert(blogId=BLOG_ID, body=body).execute()
            print("🎉 GitHub Actions 포스팅 성공!")
        else:
            print("❌ 콘텐츠 생성 실패로 포스팅을 건너뜁니다.")

if __name__ == "__main__":
    run_bot()

