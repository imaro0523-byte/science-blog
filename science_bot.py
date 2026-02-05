import os
import json
import time
import re
import requests
import feedparser
import trafilatura
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
MODEL_NAME = "gemini-3.0-flash-preview"

# =========================================================
# [함수 2] 뉴스 리스트 가져오기
# =========================================================
def get_science_news_list():
    print("🔍 구글 뉴스 과학 섹션 헤드라인 리스트 검색...")
    rss_url = "https://news.google.com/rss/headlines/section/topic/SCIENCE?hl=ko&gl=KR&ceid=KR:ko"
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
# [함수 3] 중복 포스팅 확인
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
                return text[:3000]
        print("⚠️ 본문 추출 실패 - 제목만 사용")
        return None
    except Exception as e:
        print(f"⛔ 크롤링 에러: {e}")
        return None

# =========================================================
# [함수 5] 과학 원리 심층 리서치 (★ 핵심 추가)
# =========================================================
def research_science_principle(news_title, article_content):
    """뉴스 속 과학 원리를 깊이 있게 분석"""
    print("🔬 AI가 과학 원리 심층 분석 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    context = f"기사 내용: {article_content[:1500]}" if article_content else f"제목만 있음: {news_title}"
    
    prompt = f"""
    다음 과학 뉴스를 분석하여 독자들이 알아야 할 과학 지식을 정리해줘.
    
    {context}
    
    다음 항목들을 각각 3-4문장으로 상세히 설명해줘:
    1. 핵심 과학 원리: 이 뉴스의 기반이 되는 과학 법칙, 이론, 메커니즘을 교과서적으로 정확하게 설명 (예: 양자역학, DNA 복제, 광합성, 상대성이론 등)
    2. 실험/연구 방법론: 어떤 실험 장비나 연구 방법을 사용했는지 (예: 전자현미경, PCR, 분광기, 통계 분석 등)
    3. 역사적 맥락: 이 발견이 과거 어떤 연구의 연장선상인지, 관련된 노벨상이나 중요한 발견이 있는지
    4. 학계 반응: 이 연구가 과학계에서 어떻게 평가받는지, 재현성이나 신뢰도는 어떤지
    5. 미래 응용: 이 발견이 5-10년 후 어떤 기술로 이어질 수 있는지 구체적 예측
    
    JSON 형식으로만 출력:
    {{
      "scientific_principle": "...",
      "research_method": "...",
      "historical_context": "...",
      "academic_response": "...",
      "future_application": "..."
    }}
    """
    
    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4}  # 과학적 정확성을 위해 낮게
        }
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        
        if res.status_code == 200:
            raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                research_data = json.loads(json_match.group())
                print("✅ 과학 원리 리서치 완료")
                return research_data
    except Exception as e:
        print(f"⚠️ 리서치 실패: {e}")
    
    return None

# =========================================================
# [함수 6] 팩트 체크 레이어 (★ 과학적 오류 방지)
# =========================================================
def fact_check_content(content_draft, news_title):
    """작성된 글의 과학적 정확성 검증"""
    print("🔍 AI가 과학적 사실 오류 체크 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    당신은 과학 저널 편집장입니다. 아래 글을 검토하여 과학적 오류가 있는지 확인해주세요.
    
    [원본 뉴스 제목]
    {news_title}
    
    [작성된 초안]
    {content_draft[:1500]}
    
    다음 항목을 체크하세요:
    1. 과학적 사실 오류가 있는가? (법칙, 이론, 수치 등)
    2. 과장되거나 비약된 주장이 있는가?
    3. 인과관계가 명확하지 않은 부분이 있는가?
    4. 출처나 근거가 불분명한 주장이 있는가?
    
    JSON 형식으로 출력:
    {{
      "has_errors": true/false,
      "errors": ["오류 내용 1", "오류 내용 2"],
      "suggestions": ["수정 제안 1", "수정 제안 2"]
    }}
    
    만약 오류가 없으면:
    {{
      "has_errors": false,
      "errors": [],
      "suggestions": []
    }}
    """
    
    try:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2}
        }
        res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        
        if res.status_code == 200:
            raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
            json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if json_match:
                fact_check = json.loads(json_match.group())
                if fact_check.get('has_errors'):
                    print(f"⚠️ 발견된 오류: {len(fact_check.get('errors', []))}개")
                    for error in fact_check.get('errors', []):
                        print(f"  - {error}")
                else:
                    print("✅ 과학적 오류 없음")
                return fact_check
    except Exception as e:
        print(f"⚠️ 팩트 체크 실패: {e}")
    
    return None

# =========================================================
# [함수 7] 키워드 추출
# =========================================================
def get_search_keywords(news_title):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    prompt = f"뉴스 제목: '{news_title}'. 이 뉴스의 핵심 영어 명사 키워드 3개를 콤마로 구분해줘. 설명 없이 단어만."
    try:
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers={'Content-Type': 'application/json'})
        return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "science, technology"

# =========================================================
# [함수 8] 이미지 검색
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
                print("⚠️ 이미지 부족")
                return []
    except Exception as e:
        print(f"⛔ 이미지 검색 에러: {e}")
    return []

# =========================================================
# [함수 9] 후킹 제목 생성
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
    4. 부가 설명 없이 제목 한 줄만 출력.
    
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
            clean_title = new_title.split('\n')[0]
            return clean_title.replace('"', '').replace("'", "").replace("**", "").replace("*", "")
    except:
        pass
    return news_title

# =========================================================
# [함수 10] 심층 과학 칼럼 작성 (★ 대폭 강화)
# =========================================================
def generate_deep_science_content(news, image_urls, article_content=None, research_data=None):
    print(f"🧠 AI({MODEL_NAME})가 심층 과학 칼럼 작성 중...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    
    img1 = f'<img src="{image_urls[0]}" alt="과학 이미지 1" style="width:100%; border-radius:10px; margin:20px 0;">' if len(image_urls)>0 else ""
    img2 = f'<img src="{image_urls[1]}" alt="과학 이미지 2" style="width:100%; border-radius:10px; margin:20px 0;">' if len(image_urls)>1 else ""

    # 리서치 데이터 통합
    research_section = ""
    if research_data:
        research_section = f"""
[참고할 과학 지식]
- 핵심 원리: {research_data.get('scientific_principle', 'N/A')}
- 연구 방법: {research_data.get('research_method', 'N/A')}
- 역사적 맥락: {research_data.get('historical_context', 'N/A')}
- 학계 반응: {research_data.get('academic_response', 'N/A')}
- 미래 응용: {research_data.get('future_application', 'N/A')}
"""

    article_section = f"""
[원문 기사 내용]
{article_content[:1500]}
""" if article_content else ""

    prompt = f"""
당신은 과학 유튜버처럼 쉽고 재미있지만, **절대적으로 정확한** 과학 설명을 하는 블로거입니다.

[뉴스]
제목: {news.title}
링크: {news.link}

{article_section}

{research_section}

[작성 가이드 - 과학 애호가들을 위한]
1. **정확성 최우선**: 과학적 사실은 절대 과장하거나 비약하지 않음
2. **원리 깊이 파기**: 표면적 설명이 아니라, "왜 그렇게 작동하는가"를 분자/원자 수준까지 설명
3. **실험 과정 구체화**: 연구진이 어떤 장비와 방법을 썼는지 상세히
4. **수식/그래프 언급**: 가능하면 공식이나 데이터를 언급 (복잡한 수식은 말로 풀어서)
5. **비유의 정확성**: 비유를 쓸 때도 과학적으로 올바른 비유만 사용
6. **한계 명시**: 이 연구의 한계나 추가 검증이 필요한 부분도 솔직히 언급
7. **학계 논쟁 소개**: 이 주제에 대한 다른 의견이나 논쟁이 있다면 소개

[HTML 구조]
<h2>🔬 [호기심 자극하는 소제목]</h2>
<p>[도입: 이 발견이 왜 중요한지 - 3문장]</p>

{img1}

<h2>📚 과학 원리의 기초: [핵심 개념] 완전 정복</h2>
<p>[원리를 교과서 수준으로 정확하게 설명 - 6문장 이상]</p>
<ul>
  <li>메커니즘 1 (예: 분자 수준 상호작용)</li>
  <li>메커니즘 2 (예: 에너지 전환 과정)</li>
  <li>메커니즘 3 (예: 시스템 전체 동작)</li>
</ul>

<h2>🧪 연구진은 어떻게 발견했나</h2>
<p>[실험 장비, 샘플 크기, 통계 분석, 대조군 설정 등 구체적 방법론 - 5문장 이상]</p>

{img2}

<h2>🔗 과거부터 현재까지의 여정</h2>
<p>[이 발견의 역사적 맥락, 관련된 과거 연구, 노벨상 수상 등 - 4문장 이상]</p>

<h2>🚀 10년 후, 우리는 이걸 어떻게 쓸까</h2>
<p>[구체적인 응용 기술 예측, 단 과학적 근거가 있는 것만 - 4문장 이상]</p>

<h2>⚠️ 아직 풀리지 않은 퍼즐</h2>
<p>[이 연구의 한계, 재현성 이슈, 추가 검증 필요 사항 - 3문장 이상]</p>

<p><strong>결론:</strong> [한 문장으로 핵심 정리]</p>
<hr>
<p style="color:grey; font-size:0.8em; text-align:center;">📰 출처: <a href="{news.link}">{news.title}</a></p>

[필수 규칙]
- HTML 태그만 출력 (```html 블록 절대 금지)
- 친근한 해요체 사용
- 전문 용어는 반드시 괄호로 쉽게 풀이 (예: 광합성(빛을 이용해 포도당을 만드는 과정))
- 각 섹션마다 최소 3문장 이상 작성
- 과학적 사실은 100% 정확하게, 불확실한 부분은 "추정됩니다", "연구 중입니다"로 표현
- 문단당 3~5문장 유지
"""
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}], 
        "generationConfig": {
            "temperature": 0.5,  # 과학적 정확성을 위해 적당히
            "topP": 0.9,
            "topK": 40,
            "maxOutputTokens": 2048
        }
    }
    
    for attempt in range(3):
        try:
            res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
            if res.status_code == 200:
                content = res.json()['candidates'][0]['content']['parts'][0]['text']
                cleaned = content.replace("```html", "").replace("```", "").strip()
                
                # 너무 짧으면 재시도
                if len(cleaned) < 800:
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
        # 1. Blogger 서비스 연결
        creds = Credentials.from_authorized_user_info(TOKEN_JSON)
        service = build('blogger', 'v3', credentials=creds)

        # 2. 뉴스 리스트 가져오기
        news_list = get_science_news_list()
        if not news_list:
            print("❌ 가져온 뉴스가 없습니다.")
            return

        # 3. 중복 확인 및 뉴스 선택
        target_news = None
        
        for news in news_list:
            print(f"\n{'='*60}")
            print(f"🔎 기사 확인 중: {news.title}")
            if check_is_duplicate(service, news.title):
                print(f"🚫 [중복] 이미 포스팅된 기사입니다. 다음 기사로 넘어갑니다.")
                continue
            else:
                print(f"✅ [통과] 새로운 기사입니다! 작업을 시작합니다.")
                target_news = news
                break
        
        if not target_news:
            print("😴 오늘은 모든 상위 뉴스가 이미 포스팅되었습니다.")
            return

        print(f"\n{'='*60}")
        print(f"✅ 선택된 뉴스: {target_news.title}")
        print(f"{'='*60}\n")

        # ★★★ 핵심 파이프라인: 과학적 정확성 우선 ★★★
        # 1단계: 원문 크롤링
        article_content = fetch_article_content(target_news.link)
        
        # 2단계: 과학 원리 심층 리서치
        research_data = research_science_principle(target_news.title, article_content)
        
        # 3단계: 이미지 검색
        keywords = get_search_keywords(target_news.title)
        images = get_relevant_images_webp(keywords)
        
        # 4단계: 심층 과학 칼럼 작성
        content = generate_deep_science_content(
            target_news,
            images,
            article_content,
            research_data
        )
        
        if not content:
            print("❌ 글 작성 실패")
            return

        # 5단계: 팩트 체크 (과학적 오류 검증)
        fact_check = fact_check_content(content, target_news.title)
        if fact_check and fact_check.get('has_errors'):
            print("⚠️ 과학적 오류가 발견되어 재작성이 필요합니다.")
            print("오류 내용:")
            for error in fact_check.get('errors', []):
                print(f"  - {error}")
            # 실제 운영에서는 여기서 재작성 로직을 추가할 수 있음
            # 지금은 그냥 진행
        
        # 6단계: 제목 생성 및 업로드
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

