import os
import json
import time
import requests
import feedparser
import trafilatura
import re
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
# [함수 1] 모델 선택
# =========================================================
MODEL_NAME = "gemini-2.5-flash"  # 최신 모델로 수정

# =========================================================
# [함수 2] 테크 뉴스 리스트 가져오기
# =========================================================
def get_tech_news_list():
    print("🔍 구글 뉴스 [테크/IT] 섹션 헤드라인 검색...")
    rss_url = "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        if feed.entries:
            top_5_news = feed.entries[:5]
            print(f"✅ 총 {len(top_5_news)}개의 최신 테크 뉴스를 가져왔습니다.")
            return top_5_news
    except Exception as e:
        print(f"⛔ 뉴스 검색 에러: {e}")
    return []

# =========================================================
# [함수 3] 중복 포스팅 확인 함수
# =========================================================
def check_is_duplicate(service, news_title):
    try:
        posts = service.posts().list(blogId=BLOG_ID, maxResults=10).execute()
        items = posts.get('items', [])
        for post in items:
            if news_title in post.get('content', ''):
                return True
        return False
    except Exception as e:
        print(f"⚠️ 중복 확인 중 에러 (진행함): {e}")
        return False

# =========================================================
# [함수 4] 원문 기사 본문 크롤링 (★ 새로 추가)
# =========================================================
def fetch_article_content(url):
    """뉴스 원문을 크롤링하여 본문 텍스트 추출"""
    print(f"📰 기사 본문 가져오는 중: {url}")
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False)
            if text and len(text) > 100:
                print(f"✅ 본문 {len(text)}자 추출 성공")
                return text[:3000]  # 너무 길면 앞부분만
        print("⚠️ 본문 추출 실패 - 제목만 사용")
        return None
    except Exception as e:
        print(f"⛔ 크롤링 에러: {e}")
        return None

# =========================================================
# [함수 5] 관련 정보 추가 검색 (★ 새로 추가)
# =========================================================
def research_tech_topic(news_title, article_content):
    """뉴스 주제에 대한 배경 지식 및 심층 정보 검색"""
    print("🔬 AI가 추가 리서치 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    # 기사 내용이 있으면 함께 분석
    context = f"기사 내용: {article_content[:1000]}" if article_content else f"제목만 있음: {news_title}"
    
    prompt = f"""
    다음 테크 뉴스에 대해 독자들이 알아야 할 배경 지식을 정리해줘.
    
    {context}
    
    다음 항목들을 각각 2-3문장으로 요약해줘:
    1. 핵심 기술 원리 (예: 이 반도체 공정이 뭔지, LLM이 어떻게 작동하는지)
    2. 관련 업계 동향 (경쟁사 상황, 시장 트렌드)
    3. 과거 비슷한 사례 (역사적 맥락)
    4. 전문가들의 주요 의견 (찬반 논쟁이 있다면)
    
    JSON 형식으로만 출력:
    {{
      "tech_principle": "...",
      "industry_trend": "...",
      "historical_context": "...",
      "expert_opinions": "..."
    }}
    """
    
    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.5}
        }
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        
        if res.status_code == 200:
            raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
            # JSON 파싱 시도
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                research_data = json.loads(json_match.group())
                print("✅ 리서치 완료")
                return research_data
    except Exception as e:
        print(f"⚠️ 리서치 실패: {e}")
    
    return None

# =========================================================
# [함수 6] 키워드 추출
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"뉴스 제목: '{news_title}'. 이 뉴스의 핵심 '영어' 테크 키워드 3개를 콤마로 구분해줘. (예: AI, Smartphone, Semiconductor)"
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "technology, innovation"

# =========================================================
# [함수 7] 이미지 검색
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
                return []
    except Exception as e:
        print(f"⛔ 이미지 검색 에러: {e}")
    return []

# =========================================================
# [함수 8] 후킹 제목 생성
# =========================================================
def generate_viral_title(news_title):
    print("🎣 AI가 클릭을 유도하는 테크 제목을 짓고 있습니다...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    너는 인기 IT/테크 블로그의 메인 에디터야. 
    아래 뉴스 제목을 사람들이 무조건 클릭하게 만드는 매력적인 제목으로 바꿔줘.
    
    [원래 제목]
    {news_title}
    
    [제목 작성 규칙]
    1. **트렌디함**: 최신 기술 트렌드를 반영하여 호기심을 자극해. (존댓말 사용)
    2. **핵심 요약**: 괄호 '()' 안에 핵심 기술명이나 기업명, 또는 효과를 적어.
    3. 따옴표 제외.
    
    [예시]
    - 원제: 애플, 새로운 아이폰 공개
    -> 아이폰 16, 무엇이 달라졌을까? 혁신 포인트 총정리 (애플 이벤트)
    - 원제: 엔비디아 주가 폭등, AI 칩 수요 증가
    -> AI 시대의 심장, 엔비디아가 세상을 바꾸는 법 (GPU 혁명)
    
    [출력]
    완성된 제목 한 줄만 출력해.
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
# [함수 9] 심층 분석 글 작성 (★ 대폭 강화)
# =========================================================
def generate_deep_content_with_images(news, image_urls, article_content=None, research_data=None):
    print(f"🧠 AI({MODEL_NAME})가 심층 분석 칼럼 작성 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    img1 = f'<img src="{image_urls[0]}" alt="Tech Image 1" style="width:100%; border-radius:10px; margin:20px 0;">' if len(image_urls)>0 else ""
    img2 = f'<img src="{image_urls[1]}" alt="Tech Image 2" style="width:100%; border-radius:10px; margin:20px 0;">' if len(image_urls)>1 else ""

    # 리서치 데이터를 프롬프트에 통합
    research_section = ""
    if research_data:
        research_section = f"""
[참고할 배경 지식]
- 기술 원리: {research_data.get('tech_principle', 'N/A')}
- 업계 동향: {research_data.get('industry_trend', 'N/A')}
- 역사적 맥락: {research_data.get('historical_context', 'N/A')}
- 전문가 의견: {research_data.get('expert_opinions', 'N/A')}
"""

    article_section = f"""
[원문 기사 내용]
{article_content[:1500]}
""" if article_content else ""

    prompt = f"""
    당신은 10년 경력의 IT/테크 전문 칼럼니스트입니다.
    아래 뉴스를 단순 요약이 아닌, **심층 분석 칼럼**으로 작성하세요.

    [뉴스 기본 정보]
    제목: {news.title}
    링크: {news.link}
    
    {article_section}
    
    {research_section}
    
    [작성 가이드]
    1. **단순 사실 나열 금지**: 뉴스 내용을 그대로 옮기지 말고, "왜 이게 중요한가"를 분석
    2. **기술 원리 깊게 파기**: 해당 기술이 작동하는 방식을 비유를 들어 설명
    3. **업계 맥락 제공**: 경쟁사, 과거 사례, 시장 반응 등을 언급
    4. **미래 전망**: 이 기술이 3년 후 우리 삶을 어떻게 바꿀지 구체적으로 예측
    5. **비판적 시각**: 긍정적인 면만이 아니라 우려되는 점도 공정하게 다룸
    
    [HTML 구조]
    <h2>🔥 [독자의 시선을 끄는 소제목]</h2>
    <p>[후킹: 독자가 공감할 만한 질문이나 상황 제시 - 3문장]</p>
    
    {img1}
    
    <h2>🧐 기술의 본질: [핵심 기술명]이란 무엇인가</h2>
    <p>[원리 설명 - 비유 활용, 5문장 이상]</p>
    <ul>
      <li>핵심 포인트 1</li>
      <li>핵심 포인트 2</li>
      <li>핵심 포인트 3</li>
    </ul>
    
    <h2>📊 업계는 지금 어떻게 움직이나</h2>
    <p>[경쟁사 동향, 시장 반응, 역사적 맥락 - 4문장 이상]</p>
    
    {img2}
    
    <h2>🔮 3년 후, 우리 삶은 어떻게 바뀔까</h2>
    <p>[구체적 시나리오 - 소비자 관점에서 - 4문장 이상]</p>
    
    <h2>⚠️ 그런데 말입니다 (우려되는 점)</h2>
    <p>[비판적 분석 - 리스크, 논란, 한계점 - 3문장 이상]</p>
    
    <p><strong>결론:</strong> [한 문장 정리]</p>
    <p><small>📰 출처: <a href="{news.link}">{news.title}</a></small></p>
    
    [필수 규칙]
    - HTML 태그만 출력 (```html 블록 절대 금지)
    - 해요체 사용
    - 전문 용어는 반드시 괄호로 쉽게 풀이
    - 각 섹션마다 최소 3문장 이상 작성
    - 구체적인 숫자, 사례, 인용 활용
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}], 
        "generationConfig": {
            "temperature": 0.6,  # 창의성 향상
            "topP": 0.9,
            "topK": 40,
            "maxOutputTokens": 2048  # 긴 글 생성 가능
        }
    }
    
    for attempt in range(3):
        try:
            res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
            if res.status_code == 200:
                content = res.json()['candidates'][0]['content']['parts'][0]['text']
                cleaned = content.replace("```html", "").replace("```", "").strip()
                
                # 너무 짧으면 재시도
                if len(cleaned) < 500:
                    print(f"⚠️ 글이 너무 짧음 ({len(cleaned)}자), 재시도...")
                    time.sleep(3)
                    continue
                    
                return cleaned
            elif res.status_code == 429:
                print("⏳ Rate limit, 30초 대기...")
                time.sleep(30)
        except Exception as e:
            print(f"❌ 시도 {attempt+1} 실패: {e}")
            time.sleep(5)
    
    return None

# =========================================================
# [메인 실행] (★ 파이프라인 통합)
# =========================================================
def run_bot():
    try:
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        news_list = get_tech_news_list()
        if not news_list:
            print("❌ 뉴스 없음")
            return

        target_news = None
        for news in news_list:
            print(f"\n{'='*60}")
            print(f"🔎 검토 중: {news.title}")
            if check_is_duplicate(service, news.title):
                print("🚫 중복 - 스킵")
                continue
            else:
                target_news = news
                break
        
        if not target_news:
            print("😴 새 뉴스 없음")
            return

        print(f"\n{'='*60}")
        print(f"✅ 선택됨: {target_news.title}")
        print(f"{'='*60}\n")

        # ★★★ 핵심 변경: 3단계 리서치 파이프라인 ★★★
        # 1단계: 원문 크롤링
        article_content = fetch_article_content(target_news.link)
        
        # 2단계: 추가 리서치
        research_data = research_tech_topic(target_news.title, article_content)
        
        # 3단계: 이미지 검색
        keywords = get_search_keywords(target_news.title)
        images = get_relevant_images_webp(keywords)
        
        # 4단계: 심층 칼럼 작성 (모든 데이터 활용)
        content = generate_deep_content_with_images(
            target_news, 
            images, 
            article_content,  # 원문 전달
            research_data     # 리서치 결과 전달
        )
        
        if not content:
            print("❌ 글 작성 실패")
            return

        # 5단계: 제목 생성 및 업로드
        final_title = generate_viral_title(target_news.title)
        
        print("\n📤 블로그 업로드 중...")
        body = {"kind": "blogger#post", "title": final_title, "content": content}
        service.posts().insert(blogId=BLOG_ID, body=body).execute()
        print(f"\n🎉 포스팅 완료!")
        print(f"📝 제목: {final_title}")
        print(f"📏 본문 길이: {len(content)}자")
        
    except Exception as e:
        print(f"⛔ 치명적 오류: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    run_bot()
