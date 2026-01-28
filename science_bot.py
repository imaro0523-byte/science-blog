import os
import json
import requests
import feedparser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# GitHub Secrets에서 정보 가져오기
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BLOG_ID = os.environ.get('BLOG_ID')
# 금고에 넣어둔 JSON 텍스트를 파이썬 객체로 변환
CLIENT_JSON = json.loads(os.environ.get('CLIENT_JSON'))
TOKEN_JSON = json.loads(os.environ.get('TOKEN_JSON'))

MODEL_NAME = "gemini-2.0-flash" # 성공했던 모델 그대로 사용

def get_latest_news():
    rss_url = "https://news.google.com/rss/search?q=science+when:1d&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(rss_url)
    return feed.entries[0] if feed.entries else None

def generate_content(news):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"당신은 과학 블로거입니다. 다음 뉴스를 HTML로 요약하세요: {news.title}"
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload)
    return response.json()['candidates'][0]['content']['parts'][0]['text']

def run_bot():
    news = get_latest_news()
    if news:
        # TOKEN_JSON 데이터를 사용해 인증
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)
        
        content = generate_content(news)
        body = {"kind": "blogger#post", "title": f"[과학뉴스] {news.title}", "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print("✅ GitHub Actions 포스팅 성공!")

if __name__ == "__main__":
    run_bot()