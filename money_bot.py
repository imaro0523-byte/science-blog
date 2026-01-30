import os
import json
import time
import requests
import feedparser
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# =========================================================
# [설정 구역]
# =========================================================
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
BLOG_ID = os.environ.get('MONEY_BLOG_ID')
PEXELS_API_KEY = os.environ.get('PEXELS_API_KEY')

try:
    CLIENT_JSON = json.loads(os.environ.get('CLIENT_JSON'))
    TOKEN_JSON = json.loads(os.environ.get('TOKEN_JSON'))
except:
    print("⛔ 설정 로딩 실패")
    exit(1)

MODEL_NAME = "gemini-2.5-flash"

# =========================================================
# [함수 1] 실시간 코인 가격 & 탐욕 지수 가져오기 (NEW)
# =========================================================
def get_market_data():
    data = {"btc": 0, "btc_change": 0, "eth": 0, "eth_change": 0, "fng_value": 0, "fng_class": "Unknown"}
    
    # 1. CoinGecko API (가격)
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=krw&include_24hr_change=true"
        res = requests.get(url, timeout=10).json()
        data['btc'] = res['bitcoin']['krw']
        data['btc_change'] = res['bitcoin']['krw_24h_change']
        data['eth'] = res['ethereum']['krw']
        data['eth_change'] = res['ethereum']['krw_24h_change']
    except Exception as e:
        print(f"⚠️ 가격 정보 가져오기 실패: {e}")

    # 2. Alternative.me API (공포/탐욕 지수)
    try:
        fng_res = requests.get("https://api.alternative.me/fng/", timeout=10).json()
        data['fng_value'] = int(fng_res['data'][0]['value'])
        data['fng_class'] = fng_res['data'][0]['value_classification']
    except Exception as e:
        print(f"⚠️ 탐욕 지수 가져오기 실패: {e}")
        
    return data

# =========================================================
# [함수 2] 도파민 대시보드 HTML 생성 (NEW)
# =========================================================
def create_dashboard_html(data):
    # 한국인은 빨간색이 상승, 파란색이 하락
    btc_color = "red" if data['btc_change'] >= 0 else "blue"
    btc_arrow = "▲" if data['btc_change'] >= 0 else "▼"
    eth_color = "red" if data['eth_change'] >= 0 else "blue"
    eth_arrow = "▲" if data['eth_change'] >= 0 else "▼"
    
    # 탐욕 지수에 따른 이모지
    fng_emoji = "😐"
    if data['fng_value'] >= 75: fng_emoji = "🤑 극단적 탐욕 (매도 타이밍?)"
    elif data['fng_value'] >= 55: fng_emoji = "😋 탐욕 (불장 진입)"
    elif data['fng_value'] <= 25: fng_emoji = "😱 극단적 공포 (저점 매수?)"
    elif data['fng_value'] <= 45: fng_emoji = "😨 공포 (주워담을 때)"

    html = f"""
    <div style="background-color: #f8f9fa; border: 2px solid #333; border-radius: 10px; padding: 15px; margin-bottom: 20px; font-family: sans-serif;">
        <h3 style="margin-top: 0; text-align: center; color: #333;">🔥 실시간 시장 도파민 지수</h3>
        <hr style="border: 1px dashed #ccc;">
        <div style="display: flex; justify-content: space-around; text-align: center;">
            <div>
                <div style="font-size: 14px; color: #666;">비트코인 (BTC)</div>
                <div style="font-size: 18px; font-weight: bold; color: {btc_color};">
                    {btc_arrow} {data['btc']:,.0f}원 <small>({data['btc_change']:.2f}%)</small>
                </div>
            </div>
            <div>
                <div style="font-size: 14px; color: #666;">이더리움 (ETH)</div>
                <div style="font-size: 18px; font-weight: bold; color: {eth_color};">
                    {eth_arrow} {data['eth']:,.0f}원 <small>({data['eth_change']:.2f}%)</small>
                </div>
            </div>
        </div>
        <div style="background-color: #eee; border-radius: 5px; padding: 10px; margin-top: 15px; text-align: center;">
            <strong>공포/탐욕 지수:</strong> <span style="color: #d35400; font-weight: bold;">{data['fng_value']}점</span>
            <br>{fng_emoji}
        </div>
    </div>
    """
    return html

# =========================================================
# [함수 3] 코인/경제 뉴스 가져오기
# =========================================================
def get_money_news_list():
    print("🔍 코인/재테크 뉴스 검색 중...")
    # 코인텔레그래프 또는 구글 뉴스 비즈니스 섹션
    rss_url = "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        return feed.entries[:5]
    except:
        return []

# =========================================================
# [함수 4] 중복 확인
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
# [함수 5] 자극적인 제목 생성
# =========================================================
def generate_viral_title(news_title, market_data):
    print("🎣 제목 생성 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # 시장 상황을 프롬프트에 반영
    market_mood = "상승장" if market_data['btc_change'] > 0 else "하락장"
    
    prompt = f"""
   너는 100만 유튜버이자 투자 전문가야. 아래 뉴스를 사람들이 보자마자 
    '이거 안 읽으면 손해 보겠다'는 생각이 들게 강력한 제목으로 뽑아줘.
    
    [상황]: 현재 비트코인은 {market_mood}이야.
    [뉴스]: {news_title}
    
    [규칙]
    1. 도발적인 질문이나 강렬한 단어 사용 "긴급", "속보", "충격", "폭등", "폭락" 같은 단어 적극 활용.
    2. 독자에게 질문을 던지거나 경고를 날려.
    3. 괄호 안에 핵심 키워드나 '지금 봐야 함' 같은 문구 추가.
    
    [출력]: 제목 한 줄만. (따옴표 제외)
    """
    try:
        res = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
        return res.json()['candidates'][0]['content']['parts'][0]['text'].strip().replace('"', '')
    except:
        return news_title

# =========================================================
# [함수 6] 본문 생성 (대시보드 포함)
# =========================================================
def generate_content(news, image_urls, dashboard_html):
    print("🧠 본문 작성 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    img_tag = f'<img src="{image_urls[0]}" style="width:100%; border-radius:10px; margin:20px 0;">' if image_urls else ""
    
    prompt = f"""
    너는 '부의 추월차선'에 올라탄 성공한 투자자야. 
    독자들에게 이 뉴스가 어떻게 '돈'이 되는지, 혹은 어떻게 '리스크'를 피해야 하는지 HTML로 써줘.

    [뉴스]: {news.title}
    [링크]: {news.link}
    
    [글 구조 HTML]
    1. {dashboard_html} (이건 내가 넣어준 HTML이니까 그대로 제일 위에 출력해줘)
    2. <p> (도입부: 독자의 욕망을 자극. "지금 기회를 놓치면 후회합니다" 톤)</p>
    3. {img_tag}
    4. <h2>팩트 체크: 돈의 흐름이 바뀐다</h2>
    5. <p> (뉴스 분석: 세력들의 의도와 시장 반응)</p>
    6. <p>핵심 분석: 왜 이런 일이 벌어졌고, 큰손들은 어떻게 움직이는가?</p>
    7. 투자 전략: 우리는 여기서 어떤 기회를 잡아야 하는가?
    8. <h2>투자 전략: 그래서 살까 말까?</h2>
    9. <p> (대응 전략: 공격적인 투자자라면? 보수적인 투자자라면?)</p>
    10. <p style="color: grey; font-size: 0.8em;">(주의: 이 글은 투자 조언이 아니며, 모든 투자의 책임은 본인에게 있습니다.)</p>
    
    [필수] 
    - HTML 태그만 출력. 
    - 마크다운(```html) 금지.
    - 대시보드 HTML 코드는 변형하지 말고 그대로 맨 위에 넣어.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.4}}
    
    try:
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        content = res.json()['candidates'][0]['content']['parts'][0]['text']
        return content.replace("```html", "").replace("```", "").strip()
    except Exception as e:
        print(f"본문 생성 실패: {e}")
        return None

# =========================================================
# [메인 실행]
# =========================================================
def run_bot():
    try:
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)
        
        # 1. 뉴스 찾기
        news_list = get_money_news_list()
        target_news = None
        for news in news_list:
            if not check_is_duplicate(service, news.title):
                target_news = news
                break
        
        if not target_news:
            print("😴 새로운 머니 뉴스가 없습니다.")
            return

        # 2. 실시간 데이터 & 대시보드 생성 ★
        market_data = get_market_data()
        dashboard_html = create_dashboard_html(market_data)
        
        # 3. 이미지 찾기
        img_keywords = "money, bitcoin, trading, wall street"
        img_res = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": PEXELS_API_KEY}, params={"query": img_q, "per_page": 1})
        image_urls = [p['src']['original'] + "?auto=compress&fm=webp&w=800" for p in img_resp.json().get('photos', [])] if img_resp.status_code == 200 else []

        # 4. 글 작성 & 제목 생성
        content = generate_content(target_news, image_urls, dashboard_html)
        if not content: return
        
        final_title = generate_viral_title(target_news.title, market_data)

        # 5. 업로드
        body = {"kind": "blogger#post", "title": final_title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"💰 [업로드 완료] {final_title}")
        print(f"📊 대시보드 데이터: BTC {market_data['btc']}원, 탐욕지수 {market_data['fng_value']}")

    except Exception as e:
        print(f"⛔ 에러 발생: {e}")
        exit(1)

if __name__ == "__main__":
    run_bot()
