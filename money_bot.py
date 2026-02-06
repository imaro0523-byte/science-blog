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
BLOG_ID = os.environ.get('MONEY_BLOG_ID') or os.environ.get('BLOG_ID')

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
# [함수 1] 통합 시장 대시보드
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

    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=krw&include_24hr_change=true"
        res = requests.get(url, timeout=5).json()
        data['btc']['price'] = res['bitcoin']['krw']
        data['btc']['chg'] = res['bitcoin']['krw_24h_change']
    except:
        pass

    def get_style(chg):
        color = "#d63031" if chg >= 0 else "#0984e3"
        arrow = "▲" if chg >= 0 else "▼"
        return color, arrow

    items_html = ""
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
    prompt = f"뉴스 제목: '{news_title}'. 이 뉴스를 시각적으로 표현할 수 있는 영어 검색 키워드 2개만 콤마로 구분해서 알려줘. 설명 없이 단어만."
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "money, stock market"

# =========================================================
# [함수 5] 이미지 검색
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
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = text.replace('##', '').replace('###', '')
    return text

# =========================================================
# [함수 6] 본문 작성 (이미지 치환 방식 변경)
# =========================================================
def generate_content_safe(news, image_urls, dashboard_html):
    print("🧠 도파민 자극형 머니 인사이트 작성 중...")
    
    # AI에게는 '여기 이미지를 넣어라'라는 표시만 시킴
    prompt = f"""
    뉴스제목: {news.title}
    이 뉴스와 관련된 산업 섹터를 분석하고, 미국 수혜주와 한국 수혜주를 각각 1-2개씩 포함하여 투자 인사이트 글을 작성해.
    HTML 형식으로 작성하고 [[IMAGE_1]], [[IMAGE_2]] 태그를 본문에 적절히 배치해. 
    '💰 머니 헌터의 레이더'라는 섹션을 만들어 기업명과 이유를 상세히 적어줘.
    
    [뉴스 정보]
    제목: {news.title}
    링크: {news.link}
    
    [작성 절차 (Chain of Thought)]
    1. **머니 트리거(Trigger)**: 돈 욕망/공포 자극
    2. **메커니즘 해부**: 경제학적 원리(금리, 유동성, 공급망 등) 설명
    3. **히든 커넥션**: 과거 사례나 숨겨진 상관관계 연결
    4. **이미지 배치**: 
       - 첫 번째 이미지가 들어가야 할 가장 적절한 위치에 정확히 [[IMAGE_1]] 이라고 적으세요.
       - 두 번째 이미지가 들어가야 할 위치에 정확히 [[IMAGE_2]] 이라고 적으세요.

    [글의 구성 (HTML)]
    1. [[DASHBOARD]] (첫 줄 필수)
    2. <h2>(도발적인 소제목)</h2>
    3. <p>(도입부 요약)</p>
    4. (문맥에 따라 [[IMAGE_1]] 배치)
    5. <h2>돈이 움직이는 숨겨진 원리 (Background)</h2>
    6. <p>(원리 설명)</p>
    7. (문맥에 따라 [[IMAGE_2]] 배치)
    8. <h2>미래 시나리오와 당신의 기회 (Insight)</h2>
    9. <p>(전망 및 결론)</p>
    10. <hr>
    11. <p style="color:grey; font-size:0.8em; text-align:center;">(투자 책임은 본인에게 있습니다.)</p>

    위 구조에 맞춰 HTML 코드로만 출력하세요. 마크다운 사용 금지.
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    for _ in range(3):
        try:
            res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
            if res.status_code == 200:
                raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
                clean_text = clean_markdown(raw_text.replace("```html", "").replace("```", "").strip())
                
                # 1. 대시보드 교체
                final_content = clean_text.replace("[[DASHBOARD]]", dashboard_html)
                
                # 2. 이미지 태그 실제 주입 (파이썬에서 처리)
                img1_tag = f'<img src="{image_urls[0]}" style="width:100%; border-radius:12px; margin:25px 0; box-shadow: 0 10px 20px rgba(0,0,0,0.1);">' if len(image_urls) > 0 else ""
                img2_tag = f'<img src="{image_urls[1]}" style="width:100%; border-radius:12px; margin:25px 0; box-shadow: 0 10px 20px rgba(0,0,0,0.1);">' if len(image_urls) > 1 else img1_tag
                
                final_content = final_content.replace("[[IMAGE_1]]", img1_tag)
                final_content = final_content.replace("[[IMAGE_2]]", img2_tag)
                
                return final_content
            time.sleep(5)
        except Exception as e:
            print(f"작성 에러: {e}")
            time.sleep(5)
    return None

# =========================================================
# [함수 7] 제목 생성 (후보 리스트 금지 명령 추가)
# =========================================================
def generate_viral_title(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # ★ 핵심 수정: "후보를 주지 말고 딱 1개만 내놔라"고 강력하게 지시
    prompt = f"""
    뉴스 제목: '{news_title}'
    
    이 글의 블로그 제목을 딱 1개만 지어주세요.
    
    [절대 규칙]
    1. 후보 리스트(1번, 2번...)를 절대 만들지 마세요.
    2. 부가 설명 없이 오직 '제목 텍스트 한 줄'만 출력하세요.
    3. 따옴표("), 별표(*) 특수문자 절대 사용 금지.
    
    [스타일]
    사람들의 본능(돈, 공포, 기회)을 자극하는 도파민 터지는 제목.
    """
    
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        title = res.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # 안전장치: 혹시라도 엔터 치고 여러 줄을 보냈다면 첫 줄만 가져옴
        clean_title = title.split('\n')[0]
        
        # 특수문자 및 불필요한 태그 제거
        clean_title = clean_title.replace('"', '').replace("'", "").replace("**", "").replace("*", "")
        clean_title = clean_title.replace("제목:", "").strip() # "제목: "이라고 말하는 경우 대비
        
        return clean_title
    except:
        return news_title

# =========================================================
# [메인 실행]
# =========================================================
def run_bot():
    print("▶️ 도파민 머니 봇 v4.0 (이미지/제목 수정판) 시작")
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
        images = get_relevant_images_webp(keywords)
        dashboard = get_dashboard_html() 

        content = generate_content_safe(target_news, images, dashboard)
        if not content: return

        title = generate_viral_title(target_news.title)
        print(f"📤 최종 제목: {title}")
        
        body = {"kind": "blogger#post", "title": title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"🎉 업로드 완료!")

    except Exception as e:
        print(f"⛔ 오류: {e}")
        exit(1)

if __name__ == "__main__":
    run_bot()
