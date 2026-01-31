import os
import json
import time
import re
import requests
import feedparser
import yfinance as yf
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# =========================================================
# [설정 구역]
# =========================================================
print("🔧 환경변수 및 라이브러리 점검...")

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')
BLOG_ID = os.environ.get('MONEY_BLOG_ID')

if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY 누락")
    exit(1)
if not BLOG_ID:
    print("❌ BLOG_ID 누락")
    exit(1)

print(f"✅ 타겟 블로그 ID: {BLOG_ID[:5]}*****")

try:
    CLIENT_JSON = json.loads(os.environ.get('CLIENT_JSON', '{}'))
    TOKEN_JSON = json.loads(os.environ.get('TOKEN_JSON', '{}'))
except:
    print("⛔ 인증 토큰 로딩 실패")

MODEL_NAME = "gemini-2.5-flash"

# =========================================================
# [함수 1] 통합 시장 대시보드 (공포지수 제거됨)
# =========================================================
def get_dashboard_html():
    print("📊 5대 핵심 자산 데이터 수집 중...")
    
    data = {
        "btc": {"price": 0, "chg": 0, "name": "비트코인"},
        "snp": {"price": 0, "chg": 0, "name": "S&P 500"},
        "nas": {"price": 0, "chg": 0, "name": "나스닥"},
        "kos": {"price": 0, "chg": 0, "name": "코스피"},
        "kdq": {"price": 0, "chg": 0, "name": "코스닥"}
    }

    # 1. 주식 데이터 (Yahoo Finance)
    tickers = {'^GSPC': 'snp', '^IXIC': 'nas', '^KS11': 'kos', '^KQ11': 'kdq'}
    try:
        for ticker, key in tickers.items():
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) >= 2:
                close_today = hist['Close'].iloc[-1]
                close_prev = hist['Close'].iloc[-2]
                data[key]['price'] = close_today
                data[key]['chg'] = ((close_today - close_prev) / close_prev) * 100
    except Exception as e:
        print(f"⚠️ 주식 데이터 수집 실패: {e}")

    # 2. 비트코인 (CoinGecko)
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=krw&include_24hr_change=true"
        res = requests.get(url, timeout=5).json()
        data['btc']['price'] = res['bitcoin']['krw']
        data['btc']['chg'] = res['bitcoin']['krw_24h_change']
    except:
        pass

    # HTML 조립
    def get_style(chg):
        color = "#d63031" if chg >= 0 else "#0984e3" # 빨강/파랑
        arrow = "▲" if chg >= 0 else "▼"
        return color, arrow

    items_html = ""
    # 순서: 비트코인 -> 미장 -> 국장
    display_order = ['btc', 'snp', 'nas', 'kos', 'kdq']
    
    for key in display_order:
        color, arrow = get_style(data[key]['chg'])
        price_fmt = f"{data[key]['price']:,.0f}" if key == 'btc' else f"{data[key]['price']:,.2f}"
        
        items_html += f"""
        <div style="flex: 1 1 18%; min-width: 100px; margin: 5px; padding: 10px; background: #ffffff; border-radius: 8px; border: 1px solid #eee; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.03);">
            <div style="font-size: 11px; color: #888; margin-bottom: 4px;">{data[key]['name']}</div>
            <div style="font-size: 14px; font-weight: 800; color: {color}; margin-bottom: 2px;">
                {arrow} {price_fmt}
            </div>
            <div style="font-size: 10px; color: {color}; font-weight: 500;">({data[key]['chg']:.2f}%)</div>
        </div>
        """
    
    full_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin-bottom: 30px; background: #f8f9fa; border-radius: 12px; padding: 15px;">
        <h3 style="text-align: center; margin: 0 0 10px 0; font-size: 16px; color: #2d3436; letter-spacing: -0.5px;">⚡ Market Flow Check</h3>
        <div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 5px;">
            {items_html}
        </div>
    </div>
    """
    return full_html

# =========================================================
# [함수 2] 뉴스 가져오기
# =========================================================
def get_tech_news_list():
    print("🔍 구글 뉴스 [금융] 섹션 검색...")
    rss_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            return feed.entries[:5]
    except:
        pass
    return []

# =========================================================
# [함수 3] 중복 확인
# =========================================================
def check_is_duplicate(service, news_title):
    try:
        posts = service.posts().list(blogId=BLOG_ID, maxResults=10).execute()
        for post in posts.get('items', []):
            if news_title in post.get('content', ''): return True
        return False
    except:
        return False

# =========================================================
# [함수 4] 키워드 추출
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    # 마크다운 없이 순수 텍스트만 리턴하도록 프롬프트 조정
    prompt = f"뉴스 제목: '{news_title}'. 이 뉴스를 시각적으로 표현할 수 있는 영어 검색 키워드 2개만 콤마로 구분해서 알려줘. 설명 없이 단어만."
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "money, stock market"

# =========================================================
# [함수 5] 이미지 검색 (2장 확보)
# =========================================================
def get_relevant_images_webp(query):
    if not PEXELS_API_KEY: return []
    try:
        url = "https://api.pexels.com/v1/search"
        headers = {"Authorization": PEXELS_API_KEY}
        params = {"query": query, "per_page": 2, "orientation": "landscape", "size": "medium"}
        resp = requests.get(url, headers=headers, params=params)
        
        images = []
        if resp.status_code == 200:
            photos = resp.json().get('photos', [])
            for p in photos:
                images.append(p['src']['original'] + "?auto=compress&fm=webp&w=800")
        return images
    except:
        pass
    return []

# =========================================================
# [보조 함수] 마크다운 클리너
# =========================================================
def clean_markdown(text):
    # 1. **굵게** -> <b>굵게</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # 2. 불필요한 마크다운 기호 제거
    text = text.replace('##', '').replace('###', '')
    return text

# =========================================================
# [함수 6] 본문 작성 (과학 봇 스타일 Chain of Thought 적용)
# =========================================================
def generate_content_safe(news, image_urls, dashboard_html):
    print("🧠 도파민 자극형 머니 인사이트 작성 중...")
    
    # 이미지 태그 미리 생성 (없으면 빈칸)
    img1 = f'<img src="{image_urls[0]}" style="width:100%; border-radius:12px; margin:25px 0; box-shadow: 0 10px 20px rgba(0,0,0,0.1);">' if len(image_urls) > 0 else ""
    img2 = f'<img src="{image_urls[1]}" style="width:100%; border-radius:12px; margin:25px 0; box-shadow: 0 10px 20px rgba(0,0,0,0.1);">' if len(image_urls) > 1 else img1 # 2번째 없으면 1번째 재사용

    # ★ 도파민 + 과학적 분석(CoT) 프롬프트
    prompt = f"""
    당신은 자극적이지만 논리적인 '돈의 흐름 추적자'이자 금융 칼럼니스트입니다.
    독자의 도파민을 자극하면서도 깊이 있는 경제 지식을 전달하는 HTML 포스팅을 작성하세요.

    [뉴스 정보]
    제목: {news.title}
    링크: {news.link}
    
    [작성 절차 (Chain of Thought)]
    글을 쓰기 전에 다음 단계를 머릿속으로 먼저 수행하세요:
    1. **머니 트리거(Trigger) 분석**: 이 뉴스가 사람들의 '돈 욕망' 혹은 '돈 공포'를 어떻게 자극하는지 찾아내세요.
    2. **메커니즘 해부**: 이 현상의 배후에 있는 경제학적 원리(예: 금리, 유동성, 공급망, 레버리지 등)를 떠올리세요. 교과서적 정의를 쉽게 풉니다.
    3. **히든 커넥션(Connection)**: 과거의 비슷한 역사적 폭등/폭락 사례나 숨겨진 상관관계를 연결하세요.
    4. **팩트 체크**: 과장된 표현이 있더라도 수치와 팩트는 정확해야 합니다.
    5. **이미지 배치**: 아래 제공된 태그 2개를 글의 호흡이 끊기지 않는 가장 적절한 곳에 배치하세요.
       - 이미지 1: {{img1}}
       - 이미지 2: {{img2}}

    [글의 톤앤매너]
    - 지루한 뉴스 전달체 금지.
    - "당신의 지갑이 위험하다", "지금이 기회일지도 모른다"와 같이 독자를 끌어당기는 문체를 사용하세요.
    - 하지만 내용은 스마트하고 분석적이어야 합니다.
    - **중요한 단어는 <b>태그로 강조**하세요. (마크다운 ** 사용 금지)

    [글의 구성 (HTML)]
    1. [[DASHBOARD]] (이 단어 그대로 유지)
    2. <h2>(독자의 클릭을 부르는 도발적인 소제목)</h2>
    3. <p>(도입부: 뉴스 요약 + 독자의 호기심 자극)</p>
    4. (이미지 태그 1 삽입 위치)
    5. <h2>돈이 움직이는 숨겨진 원리 (Background)</h2>
    6. <p>(경제 원리 설명: 쉽고 명쾌하게)</p>
    7. (이미지 태그 2 삽입 위치)
    8. <h2>당신이 봐야 할 미래 시나리오 (Insight)</h2>
    9. <p>(시장에 미칠 파급력 분석, 위기인가 기회인가?)</p>
    10. <hr>
    11. <p style="color:grey; font-size:0.8em; text-align:center;">(이 글은 AI의 시장 분석이며, 투자의 책임은 전적으로 본인에게 있습니다.)</p>

    위 구조에 맞춰 HTML 코드로만 출력하세요.
    """
    
    # Python f-string 안에서 중괄호 {}를 쓰려면 두 번 {{}} 써야 함. 
    # 하지만 위 prompt 변수 안에서는 img1, img2 값을 직접 포맷팅 해줘야 하므로 아래에서 포맷팅 수행.
    final_prompt = prompt.replace("{{img1}}", img1).replace("{{img2}}", img2)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    for _ in range(3):
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": final_prompt}]}]}, headers={'Content-Type': 'application/json'})
            if res.status_code == 200:
                raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                clean_text = clean_markdown(raw_text.replace("```html", "").replace("```", "").strip())
                return clean_text.replace("[[DASHBOARD]]", dashboard_html)
            time.sleep(5)
        except Exception as e:
            print(f"작성 에러: {e}")
            time.sleep(5)
    return None

# =========================================================
# [함수 7] 제목 생성 (클릭률 200% 목표)
# =========================================================
def generate_viral_title(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""
    뉴스 제목: '{news_title}'
    
    이 글의 블로그 제목을 지어주세요.
    [요구사항]
    1. 사람들의 본능(돈, 공포, 기회)을 자극해야 합니다.
    2. "충격", "긴급" 같은 단어 없이도 궁금하게 만드세요.
    3. 예시: "삼성전자 위기설? 진짜 문제는 따로 있습니다", "지금 비트코인 안 사면 후회할 3가지 이유"
    4. 특수문자(따옴표, 별표 등) 절대 사용 금지.
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        title = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        return title.replace('"', '').replace("'", "").replace("**", "").replace("*", "")
    except:
        return news_title

# =========================================================
# [메인 실행]
# =========================================================
def run_bot():
    print("▶️ 도파민 머니 봇 v3.0 시작")
    try:
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        news_list = get_tech_news_list()
        if not news_list: return

        target_news = None
        for news in news_list:
            if not check_is_duplicate(service, news.title):
                target_news = news
                break
        
        if not target_news:
            print("😴 새로운 뉴스 없음")
            return

        print(f"✅ 타겟 뉴스: {target_news.title}")
        keywords = get_search_keywords(target_news.title)
        images = get_relevant_images_webp(keywords) # 이미지 2장 가져오기 시도
        dashboard = get_dashboard_html() 

        content = generate_content_safe(target_news, images, dashboard)
        if not content: return

        title = generate_viral_title(target_news.title)
        
        body = {"kind": "blogger#post", "title": title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"🎉 업로드 완료: {title}")

    except Exception as e:
        print(f"⛔ 오류: {e}")
        exit(1)

if __name__ == "__main__":
    run_bot()
