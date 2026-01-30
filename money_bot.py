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
BLOG_ID = os.environ.get('MONEY_BLOG_ID')  # 머니 블로그 ID
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')

# 환경변수 로딩 및 에러 처리
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

MODEL_NAME = "gemini-2.5-flash"

# =========================================================
# [함수 1] 대시보드 데이터 생성 (누락되었던 부분 추가)
# =========================================================
def get_dashboard_html():
    print("📊 시장 데이터(코인/공포지수) 수집 중...")
    btc, btc_chg, fng, fng_class = 0, 0, 0, "Unknown"
    
    # 1. CoinGecko (비트코인 가격)
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=krw&include_24hr_change=true"
        res = requests.get(url, timeout=5).json()
        btc = res['bitcoin']['krw']
        btc_chg = res['bitcoin']['krw_24h_change']
    except:
        pass # API 에러시 0으로 유지

    # 2. Alternative.me (공포/탐욕 지수)
    try:
        fng_res = requests.get("https://api.alternative.me/fng/", timeout=5).json()
        fng = int(fng_res['data'][0]['value'])
    except:
        pass

    # HTML 생성
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
    """
    return html

# =========================================================
# [함수 2] 금융경제 뉴스 리스트 가져오기
# =========================================================
def get_tech_news_list():
    print("🔍 구글 뉴스 [금융] 섹션 헤드라인 검색...")
    # 금융/경제 섹션 RSS
    rss_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
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
        # blogId가 없으면 에러가 나므로 확인
        if not BLOG_ID:
            print("⚠️ BLOG_ID가 설정되지 않았습니다.")
            return False
            
        posts = service.posts().list(blogId=BLOG_ID, maxResults=10).execute()
        items = posts.get('items', [])
        for post in items:
            if news_title in post.get('content', ''):
                return True
        return False
    except Exception as e:
        print(f"⚠️ 중복 확인 중 에러 (진행함): {e}")
